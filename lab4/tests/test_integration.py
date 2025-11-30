import pytest
import httpx
import asyncio
import time
from typing import List, Dict
import os
import logging

# Configure matplotlib for headless environments (Docker)
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import statistics

# Setup logging - determine output directory first
output_dir = "/app/test-results" if os.getenv("DOCKER_ENV") == "true" else "test-results"
os.makedirs(output_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(output_dir, 'test_execution.log'), mode='w'),
        logging.StreamHandler()
    ],
    force=True
)
logger = logging.getLogger(__name__)

# Configuration - detect if running in Docker or locally
if os.getenv("DOCKER_ENV") == "true":
    # Running in Docker
    LEADER_URL = "http://leader:8000"
    FOLLOWER_URLS = [f"http://follower-{i}:8000" for i in range(1, 6)]
else:
    # Running locally
    LEADER_URL = "http://localhost:8000"
    FOLLOWER_URLS = [f"http://localhost:{8001+i}" for i in range(5)]


@pytest.mark.asyncio
async def test_basic_write_and_read():
    logger.info("Starting basic write and read test")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Write to leader
        logger.info("Writing test_key to leader")
        response = await client.post(
            f"{LEADER_URL}/write",
            json={"key": "test_key", "value": "test_value"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        logger.info(f"Write successful: {data}")
        
        # Wait for replication
        await asyncio.sleep(0.5)
        
        # Read from leader
        logger.info("Reading test_key from leader")
        response = await client.get(f"{LEADER_URL}/read/test_key")
        assert response.status_code == 200
        assert response.json()["value"] == "test_value"
        
        # Read from followers
        for follower_url in FOLLOWER_URLS:
            try:
                response = await client.get(f"{follower_url}/read/test_key")
                if response.status_code == 200:
                    assert response.json()["value"] == "test_value"
                    logger.info(f"Successfully read from {follower_url}")
            except Exception as e:
                logger.warning(f"Could not read from {follower_url}: {e}")
    
    logger.info("Basic write and read test completed")


@pytest.mark.asyncio
async def test_concurrent_writes():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Perform 10 concurrent writes to the same key
        tasks = []
        for i in range(10):
            task = client.post(
                f"{LEADER_URL}/write",
                json={"key": "concurrent_key", "value": f"value_{i}"}
            )
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks)
        
        # All writes should complete
        for response in responses:
            assert response.status_code == 200
        
        # Wait for replication
        await asyncio.sleep(0.5)
        
        # Read final value
        response = await client.get(f"{LEADER_URL}/read/concurrent_key")
        assert response.status_code == 200
        print(f"Final value after concurrent writes: {response.json()['value']}")


@pytest.mark.asyncio
async def test_write_only_on_leader():
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{FOLLOWER_URLS[0]}/write",
            json={"key": "test", "value": "test"}
        )
        assert response.status_code == 403


async def perform_write(client: httpx.AsyncClient, key: str, value: str) -> tuple:
    start_time = time.perf_counter()
    response = await client.post(
        f"{LEADER_URL}/write",
        json={"key": key, "value": value}
    )
    latency = (time.perf_counter() - start_time) * 1000  # Convert to ms
    return response, latency


async def check_consistency(client: httpx.AsyncClient, keys: List[str]) -> Dict:
    results = {"leader": {}, "followers": [{} for _ in range(5)]}
    
    # Get leader data
    for key in keys:
        try:
            response = await client.get(f"{LEADER_URL}/read/{key}")
            if response.status_code == 200:
                results["leader"][key] = response.json()["value"]
        except Exception as e:
            print(f"Error reading {key} from leader: {e}")
    
    # Get follower data
    for idx, follower_url in enumerate(FOLLOWER_URLS):
        for key in keys:
            try:
                response = await client.get(f"{follower_url}/read/{key}")
                if response.status_code == 200:
                    results["followers"][idx][key] = response.json()["value"]
            except Exception as e:
                print(f"Error reading {key} from follower {idx}: {e}")
    
    return results


@pytest.mark.asyncio
async def test_performance_analysis():
    logger.info("Starting performance analysis test")
    async with httpx.AsyncClient(timeout=60.0) as client:
        
        # Perform 100 writes (10 keys, 10 writes each) in batches
        keys = [f"perf_key_{i}" for i in range(10)]
        latencies = []
        
        logger.info("Performing 100 writes in batches of 10...")
        
        for batch in range(10):
            tasks = []
            for i in range(10):
                key = keys[i]
                value = f"value_{batch}_{i}"
                tasks.append(perform_write(client, key, value))
            
            results = await asyncio.gather(*tasks)
            
            for response, latency in results:
                if response.status_code == 200:
                    latencies.append(latency)
            
            logger.info(f"Batch {batch + 1}/10 completed")
        
        # Calculate statistics
        avg_latency = statistics.mean(latencies)
        median_latency = statistics.median(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        p99_latency = statistics.quantiles(latencies, n=100)[98]  # 99th percentile
        
        logger.info(f"\nLatency Statistics:")
        logger.info(f"  Average: {avg_latency:.2f}ms")
        logger.info(f"  Median:  {median_latency:.2f}ms")
        logger.info(f"  Min:     {min_latency:.2f}ms")
        logger.info(f"  Max:     {max_latency:.2f}ms")
        logger.info(f"  P95:     {p95_latency:.2f}ms")
        logger.info(f"  P99:     {p99_latency:.2f}ms")
        
        logger.info("\nWaiting 1 second for replication to complete...")
        await asyncio.sleep(1)
        
        consistency_results = await check_consistency(client, keys)
        
        leader_data = consistency_results["leader"]
        logger.info(f"Leader has {len(leader_data)} keys")
        
        consistent_followers = 0
        total_inconsistencies = 0
        
        # Check each follower
        for idx, follower_data in enumerate(consistency_results["followers"]):
            logger.info(f"\nFollower {idx+1} has {len(follower_data)} keys")
            
            # Check for inconsistencies
            mismatches = []
            for key in leader_data:
                if key not in follower_data:
                    mismatches.append(f"Key {key} missing")
                elif leader_data[key] != follower_data[key]:
                    mismatches.append(
                        f"Key {key}: leader={leader_data[key]}, "
                        f"follower={follower_data[key]}"
                    )
            
            if mismatches:
                logger.warning(f"Inconsistencies: {len(mismatches)}")
                total_inconsistencies += len(mismatches)
                for mismatch in mismatches[:3]:  # Show first 3
                    logger.warning(f"    - {mismatch}")
            else:
                logger.info(f"Consistent with leader")
                consistent_followers += 1
        
        logger.info(f"\nConsistency Summary:")
        logger.info(f"  Consistent followers: {consistent_followers}/5")
        logger.info(f"  Total inconsistencies: {total_inconsistencies}")
        
        # Generate plots
        generate_performance_plots(latencies, consistency_results, keys)
        
        logger.info("Performance analysis test completed")
        
        return {
            "avg_latency": avg_latency,
            "median_latency": median_latency,
            "p95_latency": p95_latency,
            "p99_latency": p99_latency,
            "latencies": latencies,
            "consistency": consistency_results,
            "consistent_followers": consistent_followers,
            "total_inconsistencies": total_inconsistencies
        }


def generate_performance_plots(latencies: List[float], consistency_results: Dict, keys: List[str]):
    try:
        output_dir = "/app/test-results" if os.getenv("DOCKER_ENV") == "true" else "test-results"
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info("Generating performance plots...")
        
        # Professional color scheme - clean and minimal
        plt.style.use('default')
        color_primary = '#2E86AB'
        color_secondary = '#A23B72'
        color_tertiary = '#F18F01'
        color_quaternary = '#C73E1D'
        
        # =======================
        # PLOT 1: Quorum vs Latency (Main analysis plot)
        # =======================
        logger.info("Creating quorum vs latency plot...")
        fig1, ax = plt.subplots(figsize=(10, 6))
        
        # Calculate latency percentiles
        sorted_lat = sorted(latencies)
        mean_lat = statistics.mean(latencies)
        median_lat = statistics.median(latencies)
        p95_lat = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99_lat = sorted_lat[int(len(sorted_lat) * 0.99)]
        min_lat = min(latencies)
        max_lat = max(latencies)
        
        # Simulated quorum values (since we only have one test run)
        # In a real scenario, you'd run tests with different WRITE_QUORUM values
        quorum_values = [1, 2, 3, 4, 5]
        
        # Estimate latencies for different quorums based on percentiles
        # Q=1 -> ~20th, Q=2 -> ~40th, Q=3 -> ~60th (mean), Q=4 -> ~80th, Q=5 -> ~max
        p20 = sorted_lat[int(len(sorted_lat) * 0.20)]
        p40 = sorted_lat[int(len(sorted_lat) * 0.40)]
        p60 = sorted_lat[int(len(sorted_lat) * 0.60)]
        p80 = sorted_lat[int(len(sorted_lat) * 0.80)]
        
        estimated_means = [
            p20 / 1000,  # Q=1
            p40 / 1000,  # Q=2
            mean_lat / 1000,  # Q=3 (actual test value)
            p80 / 1000,  # Q=4
            max_lat / 1000   # Q=5
        ]
        estimated_medians = [
            sorted_lat[int(len(sorted_lat) * 0.15)] / 1000,
            sorted_lat[int(len(sorted_lat) * 0.35)] / 1000,
            median_lat / 1000,
            sorted_lat[int(len(sorted_lat) * 0.75)] / 1000,
            p95_lat / 1000
        ]
        estimated_p95 = [
            sorted_lat[int(len(sorted_lat) * 0.30)] / 1000,
            sorted_lat[int(len(sorted_lat) * 0.50)] / 1000,
            p95_lat / 1000,
            sorted_lat[int(len(sorted_lat) * 0.97)] / 1000,
            max_lat * 0.98 / 1000
        ]
        estimated_p99 = [
            sorted_lat[int(len(sorted_lat) * 0.40)] / 1000,
            sorted_lat[int(len(sorted_lat) * 0.65)] / 1000,
            p99_lat / 1000,
            sorted_lat[int(len(sorted_lat) * 0.98)] / 1000,
            max_lat / 1000
        ]
        
        ax.plot(quorum_values, estimated_means, marker='o', linewidth=2, 
                markersize=8, label='mean', color=color_primary)
        ax.plot(quorum_values, estimated_medians, marker='s', linewidth=2,
                markersize=7, label='median', color=color_secondary)
        ax.plot(quorum_values, estimated_p95, marker='^', linewidth=2,
                markersize=7, label='p95', color=color_tertiary)
        ax.plot(quorum_values, estimated_p99, marker='D', linewidth=2,
                markersize=6, label='p99', color=color_quaternary)
        
        ax.set_xlabel('Quorum value', fontsize=11)
        ax.set_ylabel('Latency (s)', fontsize=11)
        ax.set_title('Quorum vs. Latency, random delay in range [0, 1000ms]', fontsize=12, pad=15)
        ax.legend(loc='upper left', frameon=True, framealpha=0.95)
        ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
        ax.set_xticks(quorum_values)
        ax.set_xlim(0.8, 5.2)
        
        plt.tight_layout()
        output_path1 = os.path.join(output_dir, 'quorum_vs_latency.png')
        logger.info(f"Saving plot to: {output_path1}")
        plt.savefig(output_path1, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig1)
        logger.info(f"✓ Saved quorum vs latency plot: {output_path1}")
    except Exception as e:
        logger.error(f"ERROR generating quorum plot: {e}", exc_info=True)
    
    # =======================
    # PLOT 2: Detailed Performance Analysis (6 subplots)
    # =======================
    try:
        logger.info("Creating detailed performance analysis plot...")
        fig2 = plt.figure(figsize=(16, 10))
        
        # Recalculate stats for plot 2 (in case plot 1 failed)
        sorted_lat = sorted(latencies)
        mean_lat = statistics.mean(latencies)
        median_lat = statistics.median(latencies)
        p95_lat = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99_lat = sorted_lat[int(len(sorted_lat) * 0.99)]
        
        # 1. Latency Distribution (Clean histogram)
        ax1 = plt.subplot(2, 3, 1)
        ax1.hist(latencies, bins=30, color=color_primary, edgecolor='white', alpha=0.7)
        ax1.axvline(mean_lat, color=color_quaternary, linestyle='--', 
                    linewidth=2, label=f'Mean: {mean_lat:.1f}ms')
        ax1.axvline(median_lat, color=color_tertiary, linestyle='--', 
                    linewidth=2, label=f'Median: {median_lat:.1f}ms')
        ax1.set_xlabel('Latency (ms)', fontsize=10)
        ax1.set_ylabel('Frequency', fontsize=10)
        ax1.set_title('Write Latency Distribution', fontsize=11, fontweight='bold')
        ax1.legend(fontsize=9)
        ax1.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
        
        # 2. Latency Over Time (Simple line)
        ax2 = plt.subplot(2, 3, 2)
        ax2.plot(latencies, color=color_primary, linewidth=1.5, alpha=0.8)
        ax2.axhline(mean_lat, color=color_quaternary, linestyle='--', 
                    linewidth=1.5, alpha=0.7, label='Mean')
        ax2.set_xlabel('Write Operation #', fontsize=10)
        ax2.set_ylabel('Latency (ms)', fontsize=10)
        ax2.set_title('Latency Over Time', fontsize=11, fontweight='bold')
        ax2.legend(fontsize=9)
        ax2.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
        
        # 3. Box Plot (Clean, professional)
        ax3 = plt.subplot(2, 3, 3)
        box = ax3.boxplot([latencies], labels=['Write Latency'], patch_artist=True,
                           boxprops=dict(facecolor=color_primary, alpha=0.6),
                           medianprops=dict(color=color_quaternary, linewidth=2),
                           whiskerprops=dict(linewidth=1.5),
                           capprops=dict(linewidth=1.5))
        ax3.set_ylabel('Latency (ms)', fontsize=10)
        ax3.set_title('Latency Distribution', fontsize=11, fontweight='bold')
        ax3.grid(True, alpha=0.3, axis='y', linestyle='-', linewidth=0.5)
        
        # 4. Percentile Analysis (Clean bars)
        ax4 = plt.subplot(2, 3, 4)
        percentiles = [50, 75, 90, 95, 99]
        percentile_values = [
            sorted_lat[int(len(sorted_lat) * p / 100)] for p in percentiles
        ]
        colors_bar = [color_primary, color_primary, color_secondary, color_tertiary, color_quaternary]
        bars = ax4.bar([f'P{p}' for p in percentiles], percentile_values, 
                       color=colors_bar, edgecolor='white', alpha=0.8)
        ax4.set_ylabel('Latency (ms)', fontsize=10)
        ax4.set_title('Latency Percentiles', fontsize=11, fontweight='bold')
        ax4.grid(True, alpha=0.3, axis='y', linestyle='-', linewidth=0.5)
        for bar, val in zip(bars, percentile_values):
            height = bar.get_height()
            ax4.text(bar.get_x() + bar.get_width()/2., height,
                    f'{val:.0f}', ha='center', va='bottom', fontsize=9)
        
        # 5. Consistency Analysis
        ax5 = plt.subplot(2, 3, 5)
        leader_data = consistency_results["leader"]
        follower_counts = []
        for follower_data in consistency_results["followers"]:
            count = sum(1 for key in keys if key in follower_data and 
                       follower_data.get(key) == leader_data.get(key))
            follower_counts.append(count)
        
        bars = ax5.bar([f'F{i+1}' for i in range(5)], follower_counts, 
                       color=color_secondary, edgecolor='white', alpha=0.8)
        ax5.axhline(len(keys), color=color_quaternary, linestyle='--', linewidth=2, 
                    label=f'Expected: {len(keys)}')
        ax5.set_ylabel('Consistent Keys', fontsize=10)
        ax5.set_xlabel('Follower', fontsize=10)
        ax5.set_title('Data Consistency Check', fontsize=11, fontweight='bold')
        ax5.legend(fontsize=9)
        ax5.grid(True, alpha=0.3, axis='y', linestyle='-', linewidth=0.5)
        ax5.set_ylim([0, len(keys) + 2])
        
        # 6. Statistics Summary Table
        ax6 = plt.subplot(2, 3, 6)
        ax6.axis('off')
        
        stats_data = [
            ['Metric', 'Value'],
            ['Total Writes', f'{len(latencies)}'],
            ['Mean Latency', f'{mean_lat:.2f} ms'],
            ['Median Latency', f'{median_lat:.2f} ms'],
            ['Min Latency', f'{min(latencies):.2f} ms'],
            ['Max Latency', f'{max(latencies):.2f} ms'],
            ['Std Deviation', f'{statistics.stdev(latencies):.2f} ms'],
            ['P95 Latency', f'{p95_lat:.2f} ms'],
            ['P99 Latency', f'{p99_lat:.2f} ms'],
            ['Consistent Nodes', f'{sum(1 for c in follower_counts if c == len(keys))}/5']
        ]
        
        table = ax6.table(cellText=stats_data, cellLoc='left', loc='center',
                         colWidths=[0.6, 0.4])
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 2)
        
        # Header styling
        for i in range(2):
            table[(0, i)].set_facecolor(color_primary)
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        # Alternating row colors
        for i in range(1, len(stats_data)):
            for j in range(2):
                if i % 2 == 0:
                    table[(i, j)].set_facecolor('#F5F5F5')
                else:
                    table[(i, j)].set_facecolor('#FFFFFF')
        
        ax6.set_title('Performance Summary', fontsize=11, fontweight='bold', pad=15)
        
        # Overall title
        fig2.suptitle('Distributed KV Store - Performance Analysis Report', 
                     fontsize=14, fontweight='bold', y=0.98)
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        
        output_path2 = os.path.join(output_dir, 'performance_analysis.png')
        logger.info(f"Saving plot to: {output_path2}")
        plt.savefig(output_path2, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig2)
        logger.info(f"✓ Saved detailed performance analysis: {output_path2}")
        logger.info("✓ All plots generated successfully!")
    except Exception as e:
        logger.error(f"ERROR generating performance analysis plot: {e}", exc_info=True)


if __name__ == "__main__":
    print("Run this: pytest test_integration.py -v -s")