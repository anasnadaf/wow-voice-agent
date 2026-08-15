# Five call scripts

Read these aloud at http://localhost:3000/demo, one per call. Between them they
cover the four qualification checkpoints, both languages, and every way a call is
supposed to end.

After hanging up, run this to see what the agent made of it:

```bash
cd server && uv run python -m scripts.last_call
```

It prints the transcript as stored, the state the graph ended in, and the
post-call extraction — enough to tell a good call from a regression.

**Speak naturally and don't rush.** Silence ends your turn, so pause fully before
the agent replies, and let it finish before you answer.

**The call does not drop the moment the agent says goodbye.** It listens for
seven seconds first, and if you speak in that window it answers you instead of
hanging up. So expect a short pause after every ending — that is the design, not
a stall.

---

## 1 — Qualified investor

The happy path: all four checkpoints answered in order, CTA accepted.

| | say |
|---|---|
| 1 | Yes, sure, I have a couple of minutes. |
| 2 | I'm looking at it purely as an investment. |
| 3 | Nandi Hills is fine, I know that area well. |
| 4 | My budget is around one and a half crore. |
| 5 | December two thousand twenty nine works for me. |
| 6 | Yes, please have someone call me. |

**Expect:** one question per turn, in the order intent → geography → budget →
timeline, then a short pitch and the Property Expert offer. It should close
warmly and hang up on its own.

**Check:** `outcome qualified`, all four checkpoints filled, `disposition
qualified`.

---

## 2 — Location objection, budget fits

Tests the one-reframe rule: the agent may push back **once**, then must accept it.

| | say |
|---|---|
| 1 | Yeah, go ahead. |
| 2 | It'd be for my own use, we're planning to build in a few years. |
| 3 | Honestly Nandi Hills feels too far from the city for me. |
| 4 | *(after its reframe)* I hear you, but it's still too far for us. |
| 5 | Budget isn't the issue, around two crore is fine. |

**Expect:** on turn 3 it acknowledges the concern and offers exactly **one**
reframe — the Devanahalli corridor, thirty to forty minutes to the airport. On
turn 4 it must accept your answer and close politely. A second reframe is a bug.

**Check:** `geography rejected`, `objections 2`, `outcome not_qualified`.

---

## 3 — Budget below entry

Tests the graceful exit. The entry price is 92.4 lakh; you're well under.

| | say |
|---|---|
| 1 | Okay, tell me. |
| 2 | For my own use, a small plot. |
| 3 | The location's fine. |
| 4 | My budget is about forty lakh, maybe forty five. |

**Expect:** no pitch, no pressure, no discount talk. It should thank you, avoid
making it awkward, say it'll keep you in mind for suitable launches, and close.

**Check:** `budget mismatch`, `outcome not_qualified`.

---

## 4 — Switching to Hindi mid-call

Tests the language switch. Start in English, then switch and **stay** switched.

| | say |
|---|---|
| 1 | Yes, go ahead. |
| 2 | Investment ke liye dekh raha hoon. |
| 3 | Haan, Nandi Hills theek hai mere liye. |
| 4 | Budget kitna rakhna padega? |
| 5 | Theek hai, aur possession kab hai? |
| 6 | Actually, let's continue in English. |

**Expect:** it switches to Hinglish on turn 2 — **the same turn**, not the next
one — and stays there through turn 5. Replies should be conversational Hindi in
Latin script with English property terms kept as-is ("possession", "site visit",
"Property Expert"). On turn 6 it goes back to English.

**Watch for:** a reply in Devanagari script, or drifting back to English while
you're still speaking Hindi. Both are regressions.

**Check:** `language hi` until the last turn.

---

## 5 — Busy caller, callback

Tests the ending that used to cut off mid-sentence.

| | say |
|---|---|
| 1 | Yes but I'm driving right now. |
| 2 | *(if it asks when)* Tomorrow evening around six works. |
| 3 | *(if it asks anything else)* No, that's all, thanks. |

**Expect:** it acknowledges immediately and offers a specific callback window —
**no pitch first**. Critically, if it asks you a question it must **wait for your
answer** before hanging up. A call that ends while a question hangs is the bug
this script exists to catch.

**Check:** `outcome callback`, `callback time` populated, and `closing held 1` if
it asked something on the closing turn — that's the guard doing its job.

---

## Quick edge cases

Worth one short call each. Say the line as your **first** reply to the greeting.

| say | expect |
|---|---|
| Please stop calling me, remove my number. | Acknowledges, apologises, hangs up at once. No pitch, no argument. `outcome dnc` |
| Sorry, wrong number, there's no Vikram here. | Apologises and ends. Never pitches to whoever answered. `outcome abandoned` |
| No thanks, I'm not interested. | One warm sentence, no rebuttal. `outcome declined` |
| Who gave you my number? This is really annoying. | Apologises, offers one line of value, asks if you'd like it to continue. Annoyed a second time → ends gracefully. |
| *(stay silent, let background noise be picked up)* | Keeps the call alive. Noise transcribed as words must never end it. |

---

## If something looks wrong

`uv run python -m scripts.last_call 3` shows the last three calls together, which
makes a pattern obvious. The server log at `/tmp/wow-server.log` records why a
call ended — search it for `holding` or `engine finished`.

One known quirk: the model occasionally writes digits ("38 acres") where the
prompt asks for words ("thirty eight acres"). Rumik normalises those correctly,
so it sounds right — but it would mispronounce on a TTS without normalisation.
