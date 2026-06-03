import asyncio
import os
from a11y.accessibility.pipeline.pipeline_stage import _run_pipeline_stage

async def main():
    url = "file://" + os.path.abspath("test_bad_html.html")
    findings = await _run_pipeline_stage(url, "test_job", True, True)
    for f in findings:
        print(f"Rule: {f['rule_id']}, Status: {f['status']}, Reason: {f['reason']}")

if __name__ == "__main__":
    asyncio.run(main())
