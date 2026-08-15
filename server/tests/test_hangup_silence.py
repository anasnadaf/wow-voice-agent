"""A finished call should not drop the instant the agent stops speaking.

The caller may still be drawing breath to ask one more thing, so the goodbye is
followed by a listening pause: the line ends only after real silence, and a
caller who speaks up gets answered instead of cut off.
"""

import asyncio

import pytest
from pipecat.clocks.system_clock import SystemClock
from pipecat.frames.frames import EndTaskFrame, UserStartedSpeakingFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameProcessorSetup
from pipecat.utils.asyncio.task_manager import TaskManager, TaskManagerParams

from app.voice import bridge
from app.voice.bridge import EngineLLMService


class StubEngine:
    """A call that finishes on its very first turn."""

    def __init__(self, outcome="callback", resumable=True):
        self._outcome = outcome
        self._resumable = resumable
        self.done = False
        self.turns = 0
        self.resumed = 0

    @property
    def state(self):
        return {"outcome": self._outcome}

    @property
    def is_done(self):
        return self.done

    def resume(self):
        if not self._resumable:
            return False
        self.done = False
        self.resumed += 1
        return True

    async def stream_turn(self, text):
        self.turns += 1
        yield "Thank you for your time."
        self.done = True


async def make_service(engine) -> tuple[EngineLLMService, list]:
    """A service wired up enough to own real tasks, with frames captured."""
    manager = TaskManager()
    manager.setup(TaskManagerParams(loop=asyncio.get_running_loop()))
    svc = EngineLLMService(engine)
    await svc.setup(
        FrameProcessorSetup(clock=SystemClock(), task_manager=manager, pipeline_worker=None)
    )

    pushed: list = []

    async def capture(frame, direction=None):
        pushed.append(frame)

    svc.push_frame = capture  # type: ignore[method-assign]
    for name in (
        "start_processing_metrics",
        "stop_processing_metrics",
        "start_ttfb_metrics",
        "stop_ttfb_metrics",
    ):

        async def noop():
            pass

        setattr(svc, name, noop)
    return svc, pushed


def context(text="I'm busy right now"):
    return LLMContext(messages=[{"role": "user", "content": text}])


@pytest.fixture(autouse=True)
def quick_silence(monkeypatch):
    """Same behaviour, compressed so the suite stays fast."""
    monkeypatch.setattr(bridge, "HANGUP_SILENCE_S", 0.2)


async def test_the_call_does_not_end_the_moment_the_agent_stops():
    svc, pushed = await make_service(StubEngine())
    await svc._run_turn(context())
    assert not any(isinstance(f, EndTaskFrame) for f in pushed)


async def test_the_call_ends_after_the_silence_window():
    svc, pushed = await make_service(StubEngine())
    await svc._run_turn(context())
    await asyncio.sleep(0.4)
    assert any(isinstance(f, EndTaskFrame) for f in pushed)


async def test_a_caller_speaking_up_keeps_the_line_open():
    engine = StubEngine()
    svc, pushed = await make_service(engine)
    await svc._run_turn(context())

    await svc.process_frame(UserStartedSpeakingFrame(), bridge.FrameDirection.DOWNSTREAM)
    await asyncio.sleep(0.4)

    assert not any(isinstance(f, EndTaskFrame) for f in pushed)
    assert engine.resumed == 1
    assert not engine.is_done  # reopened, so the follow-up turn is answered


async def test_the_reopened_call_is_answered_and_then_settles():
    engine = StubEngine()
    svc, pushed = await make_service(engine)
    await svc._run_turn(context())
    await svc.process_frame(UserStartedSpeakingFrame(), bridge.FrameDirection.DOWNSTREAM)

    await svc._run_turn(context("Sorry, one more question"))
    assert engine.turns == 2  # the caller got an answer

    await asyncio.sleep(0.4)
    assert any(isinstance(f, EndTaskFrame) for f in pushed)


async def test_a_call_that_refuses_to_reopen_still_hangs_up():
    """A do-not-call request is not reopened by someone talking over the close.

    The guard that matters: refusing to reopen must not swallow the hangup and
    leave a finished call with the line still up.
    """
    engine = StubEngine(outcome="dnc", resumable=False)
    svc, pushed = await make_service(engine)
    await svc._run_turn(context())

    await svc.process_frame(UserStartedSpeakingFrame(), bridge.FrameDirection.DOWNSTREAM)
    await asyncio.sleep(0.4)

    assert engine.resumed == 0
    assert any(isinstance(f, EndTaskFrame) for f in pushed)


async def test_speaking_mid_call_does_not_disturb_anything():
    engine = StubEngine()
    svc, pushed = await make_service(engine)
    await svc.process_frame(UserStartedSpeakingFrame(), bridge.FrameDirection.DOWNSTREAM)
    assert engine.resumed == 0
