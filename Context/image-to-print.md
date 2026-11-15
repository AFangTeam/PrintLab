# Two image selections, then a real model

## Scope

Use this process by default for a new design or a shape-changing adaptation. Continue existing selections; assess small dimensional, color or local edits according to their impact.

1. Establish purpose, dimensions, device and material constraints, then offer comparable single-image shape concepts.
2. Let the user select one. Preserve all candidates, the chosen image, prompts, sources, hashes and original feedback. Identify silhouettes, surfaces, openings and proportions that must be retained.
3. Provide four three-view sets of the selected shape, normally front, right and top, with consistent coordinates and scale. All sets represent the same design; inspect each set's orientations and occlusion.
4. Let the user select a complete set and save both choices in `Review/design-target.json`. Show and resolve specific inconsistencies. A low-detail spatial draft may generate true orthographic views; label inferred rear/interior geometry.
5. Build the actual model against the chosen target. Original models and measurements constrain mating interfaces; the selected target controls appearance. Export views, an oblique view and necessary sections from the same geometry and inspect deviations.
6. Check interfaces, hole positions, tolerances, wall thickness, insertion paths and loads. Use a test piece derived from the same source where needed. Treat an image-generated mesh as a shape candidate.
7. Confirm colors and materials, create the final 3MF, complete the manufacturing review and slicing, obtain current task-specific print confirmation, then inspect the physical result.

## Adapting an existing model

Preserve the original, author, link, version, instructions and license. List protected mating surfaces, holes, tolerances, clips/rails and assembly/removal paths; identify editable exterior regions separately. Check protected regions and real interfaces after every revision. Recheck the original license before public sharing.

## Commands and records

Use `printlab design-check --help` for input, views and release checks. The template is `Templates/Project/Review/design-target.json`. Checking files, sources and hashes does not replace viewing the actual model. Record selection history with `printlab taste record` and lessons in `Context/taste.md`.
