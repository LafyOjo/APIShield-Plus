# Simple async load testing script.
# Fires concurrent POST requests to a given endpoint,
# measures latency, and reports average and max times.

import argparse
import asyncio
import time
import httpx


async def worker(client, url, payload, semaphore, results):
    """
    A single "worker" task that sends one POST request.
    - Uses a semaphore to limit concurrency.
    - Records how long the request takes.
    - Stores latency in the shared results list.
    """
    async with semaphore:
        start = time.perf_counter()
        resp = await client.post(url, json=payload)
        latency = time.perf_counter() - start
        results.append(latency)
        resp.raise_for_status()  # throw error if status >= 400


async def run(url: str, concurrency: int, total: int):
    """
    Orchestrates the load test:
    - Spawns N worker tasks up to 'total'.
    - Ensures only 'concurrency' workers run at the same time.
    - After all complete, prints latency stats.
    """
    payload = {"client_ip": "127.0.0.1", "auth_result": "success"}
    semaphore = asyncio.Semaphore(concurrency)
    results: list[float] = []

    # Async HTTP client handles connection pooling efficiently
    async with httpx.AsyncClient() as client:
        tasks = [
            asyncio.create_task(
                worker(client, url, payload, semaphore, results)
            )
            for _ in range(total)
        ]
        # Wait for all requests to complete
        await asyncio.gather(*tasks)

    # Compute some basic latency stats
    avg = sum(results) / len(results)
    print(f"Sent {len(results)} requests")
    print(f"Average latency: {avg:.4f}s")
    print(f"Max latency: {max(results):.4f}s")


if __name__ == "__main__":
    # CLI arguments for flexibility:
    #   --url: target endpoint to hit
    #   --concurrency: max concurrent requests
    #   --total: total number of requests to send
    parser = argparse.ArgumentParser(description="Simple load test")
    parser.add_argument("--url", default="http://localhost:8001/score")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--total", type=int, default=100)
    args = parser.parse_args()

    # Run the async test harness
    asyncio.run(run(args.url, args.concurrency, args.total))
