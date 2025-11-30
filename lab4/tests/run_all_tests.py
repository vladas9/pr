import subprocess
import sys
import time
import httpx
import asyncio
import os


async def wait_for_services():
    print("Waiting for services to be healthy...")
    
    leader_url = "http://leader:8000"
    follower_urls = [f"http://follower-{i}:8000" for i in range(1, 6)]
    
    max_attempts = 30
    attempt = 0
    
    while attempt < max_attempts:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Check leader
                leader_response = await client.get(f"{leader_url}/health")
                
                # Check all followers
                follower_responses = await asyncio.gather(
                    *[client.get(f"{url}/health") for url in follower_urls],
                    return_exceptions=True
                )
                
                # Check if all are healthy
                if leader_response.status_code == 200:
                    healthy_followers = sum(
                        1 for r in follower_responses 
                        if isinstance(r, httpx.Response) and r.status_code == 200
                    )
                    
                    if healthy_followers == 5:
                        print("All services are healthy!")
                        return True
                    else:
                        print(f"  Leader healthy, {healthy_followers}/5 followers healthy")
        except Exception as e:
            print(f"  Waiting... (attempt {attempt + 1}/{max_attempts})")
        
        attempt += 1
        await asyncio.sleep(0.5)
    
    print("Services did not become healthy in time")
    return False


def run_pytest():
    print("\n" + "="*60)
    print("Running Integration Tests")
    print("="*60 + "\n")
    
    result = subprocess.run(
        ["pytest", "test_integration.py", "-v", "-s"],
        capture_output=True
    )
    
    return result.returncode == 0


def main():
    if not asyncio.run(wait_for_services()):
        print("Failed to connect to services")
    
    print("\nWaiting .5 seconds for services to stabilize...")
    time.sleep(0.5)
    
    # Run tests
    success = run_pytest()
    
    if success:
        print("\n" + "="*60)
        print("All tests passed!")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("Some tests failed")
        print("="*60)


if __name__ == "__main__":
    main()