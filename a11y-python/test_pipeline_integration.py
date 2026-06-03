import asyncio
import sys
from a11y.accessibility.pipeline.pipeline_stage import _run_pipeline_stage

async def main():
    print("Testing new Unified Pipeline on https://example.com...")
    findings = await _run_pipeline_stage(
        url="https://example.com",
        job_id="test_job",
        run_image_audit=True,
        run_label_in_name_audit=True
    )
    print(f"SUCCESS: Pipeline executed without crashing.")
    print(f"Total findings returned: {len(findings)}")
    
    rules_fired = set(f.get('rule_id') for f in findings)
    print(f"Rules evaluated: {rules_fired}")
    
    if findings:
        print("\nSample Output Schema:")
        sample = findings[0]
        # Truncate html for display
        if 'element' in sample and 'html' in sample['element']:
            sample['element']['html'] = sample['element']['html'][:50] + "..."
        print(sample)

if __name__ == "__main__":
    asyncio.run(main())
