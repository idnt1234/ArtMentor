from ..schemas import ReferenceGoal, ReferenceItem, SampleArtwork


PUBLIC_DOMAIN_WORKS = [
    {
        "id": "great-wave",
        "title": "Under the Wave off Kanagawa (The Great Wave)",
        "artist": "Katsushika Hokusai",
        "date": "c. 1830–32",
        "image_url": "/api/sample-assets/great-wave",
        "asset_filename": "great-wave.png",
        "source_url": "https://www.metmuseum.org/art/collection/search/45434",
        "license": "Public Domain",
        "license_url": "https://creativecommons.org/publicdomain/mark/1.0/",
        "dimensions": {"composition", "narrative", "value"},
        "default_intent": "Create a dramatic sense of scale and motion while keeping the distant focal point readable.",
        "default_style": "Japanese ukiyo-e woodblock print",
    },
    {
        "id": "girl-pearl",
        "title": "Girl with a Pearl Earring",
        "artist": "Johannes Vermeer",
        "date": "c. 1665",
        "image_url": "/api/sample-assets/girl-pearl",
        "asset_filename": "girl-pearl.png",
        "source_url": "https://www.mauritshuis.nl/en/our-collection/artworks/670-girl-with-a-pearl-earring/",
        "license": "Public Domain",
        "license_url": "https://creativecommons.org/publicdomain/mark/1.0/",
        "dimensions": {"value", "color", "narrative"},
        "default_intent": "Build an intimate portrait around a quiet gaze, restrained color, and a luminous focal accent.",
        "default_style": "Dutch Golden Age portrait",
    },
    {
        "id": "wheat-field",
        "title": "Wheat Field with Cypresses",
        "artist": "Vincent van Gogh",
        "date": "1889",
        "image_url": "/api/sample-assets/wheat-field",
        "asset_filename": "wheat-field.png",
        "source_url": "https://www.metmuseum.org/art/collection/search/436535",
        "license": "Public Domain",
        "license_url": "https://creativecommons.org/publicdomain/mark/1.0/",
        "dimensions": {"color", "composition", "narrative"},
        "default_intent": "Turn the landscape into an emotionally charged rhythm of movement, depth, and color.",
        "default_style": "Post-Impressionist oil painting",
    },
]


def samples() -> list[SampleArtwork]:
    return [
        SampleArtwork(
            id=item["id"],
            title=item["title"],
            artist=item["artist"],
            date=item["date"],
            image_url=item["image_url"],
            source_url=item["source_url"],
            license=item["license"],
            default_intent=item["default_intent"],
            default_style=item["default_style"],
        )
        for item in PUBLIC_DOMAIN_WORKS[:3]
    ]


def sample_by_id(sample_id: str) -> dict | None:
    return next((item for item in PUBLIC_DOMAIN_WORKS if item["id"] == sample_id), None)


def select_references(goals: list[ReferenceGoal]) -> list[ReferenceItem]:
    selected = [
        item
        | {
            "rationale": (
                goals[index].rationale
                if index < len(goals)
                else "Study its clear visual hierarchy and deliberate focal control."
            )
        }
        for index, item in enumerate(PUBLIC_DOMAIN_WORKS)
    ]
    return [
        ReferenceItem(
            id=item["id"],
            title=item["title"],
            artist=item["artist"],
            date=item["date"],
            image_url=item["image_url"],
            source_url=item["source_url"],
            license=item["license"],
            license_url=item["license_url"],
            rationale=item["rationale"],
        )
        for item in selected[:3]
    ]
