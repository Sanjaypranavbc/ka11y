# Ka11y Video Ground Truth JSON Templates

This document provides the standard ground truth JSON templates used within the `ka11y` testing framework for validating video and audio-based rule accuracy (WCAG 1.2.x series). Each template aligns with the required input shapes for media element mapping and the expected evaluator output schemas.

## 1.2.1 — Audio-only and Video-only (Prerecorded)
```json
{
  "meta": {
    "rule": "1.2.1",
    "rule_name": "Audio-only and Video-only (Prerecorded)",
    "source_url": "synthetic",
    "scraped_at": "YYYY-MM-DD",
    "total_cases": 1,
    "description": "Synthetic ground truth for WCAG 1.2.1 accuracy testing."
  },
  "cases": [
    {
      "id": "c121-01",
      "description": "Video-only content without an alternative text track or transcript",
      "dom_attributes": {
        "tag_name": "video",
        "html_snippet": "<video src=\"animation.mp4\"></video>",
        "has_audio": false,
        "is_live": false
      },
      "media_attributes": {
        "has_transcript": false,
        "has_text_alternative": false,
        "tracks": []
      },
      "expected": {
        "wcag_1_2_1_status": "fail",
        "reason_code": "missing_video_alternative",
        "reason": "Prerecorded video-only content requires a text alternative or audio track describing the video."
      }
    }
  ]
}
```

## 1.2.2 — Captions (Prerecorded)
```json
{
  "meta": {
    "rule": "1.2.2",
    "rule_name": "Captions (Prerecorded)",
    "source_url": "synthetic",
    "scraped_at": "YYYY-MM-DD",
    "total_cases": 1,
    "description": "Synthetic ground truth for WCAG 1.2.2 accuracy testing."
  },
  "cases": [
    {
      "id": "c122-01",
      "description": "Synchronized media missing closed captions track",
      "dom_attributes": {
        "tag_name": "video",
        "html_snippet": "<video src=\"presentation.mp4\"></video>",
        "has_audio": true,
        "is_live": false
      },
      "media_attributes": {
        "has_captions_track": false,
        "tracks": []
      },
      "expected": {
        "wcag_1_2_2_status": "fail",
        "reason_code": "missing_captions",
        "reason": "Prerecorded synchronized media (video with audio) requires captions."
      }
    }
  ]
}
```

## 1.2.3 — Audio Description or Media Alternative (Prerecorded)
```json
{
  "meta": {
    "rule": "1.2.3",
    "rule_name": "Audio Description or Media Alternative (Prerecorded)",
    "source_url": "synthetic",
    "scraped_at": "YYYY-MM-DD",
    "total_cases": 1,
    "description": "Synthetic ground truth for WCAG 1.2.3 accuracy testing."
  },
  "cases": [
    {
      "id": "c123-01",
      "description": "Video with audio missing audio description or text alternative",
      "dom_attributes": {
        "tag_name": "video",
        "html_snippet": "<video src=\"movie.mp4\"></video>",
        "has_audio": true,
        "is_live": false
      },
      "media_attributes": {
        "has_audio_description_track": false,
        "has_text_alternative": false,
        "tracks": [
          {
            "kind": "captions",
            "srclang": "en"
          }
        ]
      },
      "expected": {
        "wcag_1_2_3_status": "fail",
        "reason_code": "missing_audio_description_or_alternative",
        "reason": "Prerecorded synchronized media requires an audio description or a full text alternative."
      }
    }
  ]
}
```

## 1.2.4 — Captions (Live)
```json
{
  "meta": {
    "rule": "1.2.4",
    "rule_name": "Captions (Live)",
    "source_url": "synthetic",
    "scraped_at": "YYYY-MM-DD",
    "total_cases": 1,
    "description": "Synthetic ground truth for WCAG 1.2.4 accuracy testing."
  },
  "cases": [
    {
      "id": "c124-01",
      "description": "Live synchronized media missing closed captions track",
      "dom_attributes": {
        "tag_name": "video",
        "html_snippet": "<video src=\"livestream.m3u8\"></video>",
        "has_audio": true,
        "is_live": true
      },
      "media_attributes": {
        "has_captions_track": false,
        "tracks": []
      },
      "expected": {
        "wcag_1_2_4_status": "fail",
        "reason_code": "missing_live_captions",
        "reason": "Live synchronized media requires captions."
      }
    }
  ]
}
```
