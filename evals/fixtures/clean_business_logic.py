# expected_layer: 1
# expected_verdict: pass
# rule_id: simplicity-02
import asyncio


async def gather_results(tasks):
    # return_exceptions=True is the safety net if one scrape fails
    return await asyncio.gather(*tasks, return_exceptions=True)
