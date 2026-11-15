# Batch inputs

Names below are raw MCP tool names; use the actual server namespace exposed by the client. Do not write to one job concurrently.

`submit_and_refine` takes the same job_id, panel_id, title, metric, x_unit, y_unit, calibration and series as submit_digitization, plus marker_specs:

```json
{
  "calibration": {"x": [[200, 0], [1000, 120]], "y": [[900, 0], [100, 100]], "x_scale": "linear", "y_scale": "linear"},
  "series": [{"label": "Species A; Control", "points": [[203, 202], [603, 602]]}],
  "marker_specs": [{"label": "Species A; Control", "shape": "circle", "fill": "open", "radius": 7, "stroke_width": 2, "search_radius": 8}]
}
```

Numbers illustrate the schema only; obtain actual values from the crop. Shapes: circle, square, diamond, triangle_up, triangle_down, manual. Sizes are crop pixels: radius 2..24; search_radius 1..24 (default 8); stroke_width .5..radius. Optional color is `[r,g,b]` in 0..255. Manual only needs label and shape. Exactly one spec must match every series label.

The result returns revision, overlay, patches, refined/unresolved counts and per-point coarse/candidate/selected coordinates. Retain the exact revision; do not synthesize it.

After inspecting all images, `review_and_export` takes:

```json
{
  "job_id": "same job ID",
  "reviews": [{
    "panel_id": "inspected panel ID",
    "expected_revision": "exact returned revision",
    "review_notes": "Concrete observations from source and overlay",
    "point_reviews": [{"label": "Species A; Control", "point_index": 2, "decision": "keep_coarse", "notes": "Why this coarse center is correct in the source"}]
  }],
  "coverage_notes": "Which pages/frames were checked and how every requested panel is covered"
}
```

Indices are 1-based within each series. Provide one decision for every unresolved point, or an empty list if none. This is agent QA, not a user permission prompt. Unknown/duplicate panels, obsolete revisions and incomplete reviews are rejected. Correct a wrong point by submitting/re-viewing a new revision; do not approve using boilerplate notes.

To retry export after all panels were already accepted, use export_workbook(job_id, coverage_notes). Preflight review changes are all-or-none; valid reviews remain saved if desktop export later fails. Failed staged files are diagnostic artifacts, not committed panel data. There is no cross-process same-job transaction lock; serialize job writes as for single-step tools.
