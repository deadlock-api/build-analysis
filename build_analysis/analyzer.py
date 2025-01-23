import sqlite3

from tqdm.asyncio import tqdm_asyncio

from build_analysis.api import DeadlockAPI


class BuildAnalyzer:
    def __init__(self, db_path: str = "results.db"):
        self.api = DeadlockAPI()
        self.db = sqlite3.connect(db_path)
        self._init_database()

    def _init_database(self):
        """Initialize the database schema."""
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS scored_builds (
                hero_id INTEGER PRIMARY KEY,
                build_id INTEGER,
                version INTEGER,
                hero_name TEXT,
                build_name TEXT,
                win_rate REAL,
                num_favorites INTEGER,
                total INTEGER
            )
        """
        )

    @staticmethod
    def get_build_items(build: dict) -> list[int]:
        """Extract item IDs from a build."""
        mod_categories = build["details"]["mod_categories"]
        return list({i["ability_id"] for c in mod_categories for i in c.get("mods", [])})

    async def process_hero_builds(self, hero_id: int, hero_name: str):
        """Process and analyze builds for a specific hero."""
        # Fetch and process builds
        all_hero_builds = [b for b in await self.api.get_hero_builds(hero_id) if len(b["hero_build"]["name"]) > 2]

        # Create lookup dictionaries
        hero_builds_by_id = {(b["hero_build"]["hero_build_id"], b["hero_build"]["version"]): b for b in all_hero_builds}

        processed_builds = {
            (b["hero_build_id"], b["version"]): self.get_build_items(b)
            for b in (b["hero_build"] for b in all_hero_builds)
            if not b["name"].startswith("Copy")
        }
        processed_builds = {k: v for k, v in processed_builds.items() if len(v) <= 40}

        # Fetch winrates concurrently
        scores = await self._fetch_build_scores(hero_id, hero_name, processed_builds)

        # Process and store results
        self._process_build_scores(hero_id, hero_name, scores, hero_builds_by_id)

    async def _fetch_build_scores(self, hero_id: int, hero_name: str, builds: dict) -> dict:
        """Fetch winrates for all builds concurrently."""
        tasks = [
            self.api.fetch_winrate(hero_id, ",".join(str(i) for i in sorted(items))) for build, items in builds.items()
        ]

        results = await tqdm_asyncio.gather(*tasks, desc=f"Fetching winrates for hero {hero_name}", leave=False)
        return dict(zip(builds.keys(), results))

    def _process_build_scores(self, hero_id: int, hero_name: str, scores: dict, builds_by_id: dict):
        """Process and store build scores in the database."""
        # Filter and sort scores
        valid_scores = {
            build: score
            for build, score in scores.items()
            if score and score["total"] >= self._calculate_top_percentile(scores, 0.01)
        }

        # Store top build
        self._store_top_build(hero_id, hero_name, valid_scores, builds_by_id)

    @staticmethod
    def _calculate_top_percentile(scores: dict, percentile: float = 0.01) -> int:
        """Calculate the threshold for top 1% of builds."""
        totals = [s.get("total", 0) for s in scores.values() if s]
        return sorted(totals, reverse=True)[int(len(totals) * percentile)]

    def _store_top_build(self, hero_id: int, hero_name: str, scores: dict, builds_by_id: dict):
        """Store the top build in the database."""
        if not scores:
            return

        (build_id, version), score = max(
            scores.items(),
            key=lambda x: (
                round(x[1]["wins"] / max(1, x[1]["total"]), 5),
                x[1]["total"],
            ),
        )
        build = builds_by_id[(build_id, version)]
        winrate = score["wins"] / score["total"] if score["total"] > 0 else 0.0

        print(f"Top build for {hero_name}: {build['hero_build']['name']} ({winrate:.2%})")

        self.db.execute(
            """
            REPLACE INTO scored_builds 
            (hero_id, hero_name, build_id, build_name, version, win_rate, num_favorites, total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hero_id,
                hero_name,
                build_id,
                build["hero_build"]["name"],
                version,
                round(100 * winrate, 2),
                build["num_favorites"],
                score["total"],
            ),
        )
        self.db.commit()
