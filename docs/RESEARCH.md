# Research roadmap

The strongest research question is not “Can AI score art?” It is:

> When does a multimodal critique model confuse an intentional style choice with a technical mistake, and which interaction signals help it recover?

## Data captured by the MVP

- Artwork stage, named style, original intent, and artist-confirmed intent
- Model suggestion, dimension, priority, and region
- Artist verdict: useful, not useful, or intentional
- For intentional choices, the artist's free-text design reason
- Corrected regions when the AI points at the wrong area
- Before/after image pair and per-dimension outcome
- Provider/model label for reproducibility
- Reference image, model-estimated skeletons, artist-corrected skeletons, crop boxes, style tolerance, and deterministic geometry residuals
- Pose worker image hash, model/device, latency, confidence distribution, and low-confidence joints

## Feasible student experiments

1. **Intent ablation:** compare critique usefulness with no intent, raw intent, and confirmed restatement.
2. **Style-error confusion:** measure intentional-label rate by style and critique dimension.
3. **Editable grounding:** compare model rectangle IoU with artist-corrected rectangles.
4. **Suggestion budget:** compare one, three, and unlimited suggestions on completion and usefulness.
5. **Revision alignment:** test whether useful suggestions correlate with measurable or human-rated revision improvements.
6. **Pose correction burden:** compare model confidence with the number and distance of artist keypoint corrections across photos, paintings, comics, occlusion, small figures, and extreme poses.
7. **Tolerance calibration:** measure false-positive rates for realistic, stylized, and intentional-distortion modes against teacher judgments.

## Evaluation design

Build a consented dataset rather than scraping living artists. Use public-domain works for system tests and recruit illustrators for task-based evaluation. Report agreement and uncertainty instead of treating one teacher's score as ground truth. Version prompts, model IDs, and rubrics, and separate automatic metrics from human judgments.
