import asyncio

from build_analysis.analyzer import BuildAnalyzer


async def main():
    analyzer = BuildAnalyzer()
    heroes = await analyzer.api.get_all_heroes()
    for hero_id, hero_name in heroes:
        await analyzer.process_hero_builds(hero_id, hero_name)


if __name__ == "__main__":
    asyncio.run(main())
