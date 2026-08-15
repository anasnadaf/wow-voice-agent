"""Project knowledge base for Divyasree "Whispers of the Wind" (WOW).

Facts compiled from public listings for the real project (addressofchoice, roofandfloor,
99acres, dwello, amplevaluespaces, commonfloor, Aug 2026). Where sources disagree, the
campaign brief wins — e.g. plot sizes are quoted as 1200-3199 sq.ft. and the price band
as 92.4 lakh to 2.46 crore inclusive of taxes, even though some portals list larger
signature plots and a higher top-end price.
"""

PROJECT = {
    "name": "Whispers of the Wind (WOW)",
    "developer": "Divyasree Developers",
    "developer_track_record": (
        "Established 1975; about five decades of delivery, 30+ million sq.ft. built, "
        "large share of LEED-rated assets"
    ),
    "type": "Premium 'Private Valley' villa plot community (plotted development)",
    "location": (
        "Nandi Valley near Nandi Hills, Heggadihalli Village, Doddaballapura, "
        "North Bengaluru (Karnataka 562101)"
    ),
    "setting": "Valley setting between Dibbagiri Betta and Horagina Betta with hill views",
    "total_area_acres": 38,
    "total_plots": 207,
    "plot_sizes_sqft": "1200 to 3199",
    "price_range": "92.4 lakh to 2.46 crore rupees, inclusive of taxes",
    "starting_price": "92.4 lakh rupees",
    "open_space_percent": 74,
    "clubhouse_sqft": 20000,
    "possession": "December 2029",
    "status": "Ongoing / under development",
    "rera": "PRM/KA/RERA/1250/301/PR/070525/007718",
    "target_buyers": "HNIs, CXOs and NRIs looking for a second home or long-term investment",
}

AMENITIES = [
    "20,000 sq.ft. clubhouse with wellness, fitness and social spaces",
    "Swimming pool, gym and spa",
    "Mini-theatre and amphitheatre",
    "Yoga deck and meditation areas",
    "Sports courts, futsal and putt-putt golf",
    "Eco-parks, themed parks and landscaped trails",
    "Pet park, children's play areas, walking and jogging tracks",
    "74% open spaces across the 38-acre community",
]

CONNECTIVITY = [
    "Near Nandi Hills, off the Nelamangala-Chikkaballapura road in North Bengaluru",
    "Devanahalli corridor: Kempegowda International Airport is roughly a 30-40 minute drive",
    "North Bengaluru growth corridor — aerospace park, upcoming infra and suburban rail",
    "Weekend-getaway belt: vineyards, Nandi Hills sunrise point, resorts",
]

FAQ_NOTES = [
    "Plots only — buyers build their own villa; guidelines keep the community cohesive.",
    "Price band is inclusive of taxes; exact plot pricing depends on size and position.",
    "Possession (plot registration and handover of developed community) is December 2029.",
    "RERA-registered project; number available on request.",
    "Site visits and detailed cost sheets are arranged through a Property Expert.",
]


def knowledge_block() -> str:
    """Condensed KB injected into the system prompt (kept short — this rides every turn)."""
    amenities = "; ".join(AMENITIES)
    connectivity = "; ".join(CONNECTIVITY)
    faq = " ".join(FAQ_NOTES)
    return (
        f"- Project: {PROJECT['name']} by {PROJECT['developer']} — {PROJECT['type']}.\n"
        f"- Developer: {PROJECT['developer_track_record']}.\n"
        f"- Location: {PROJECT['location']}. {PROJECT['setting']}.\n"
        f"- Scale: {PROJECT['total_area_acres']} acres, {PROJECT['total_plots']} plots of "
        f"{PROJECT['plot_sizes_sqft']} sq.ft., {PROJECT['open_space_percent']}% open spaces.\n"
        f"- Pricing: {PROJECT['price_range']} (entry point {PROJECT['starting_price']}).\n"
        f"- Possession: {PROJECT['possession']} ({PROJECT['status'].lower()}).\n"
        f"- RERA: {PROJECT['rera']}.\n"
        f"- Amenities: {amenities}.\n"
        f"- Connectivity: {connectivity}.\n"
        f"- Useful answers: {faq}"
    )
