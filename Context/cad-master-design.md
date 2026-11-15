# Master geometry and shared-source test pieces

Identify the master design entry point, shared parameters, coordinate system, millimeter units, protected interfaces and derivation of each part in `Review/cad-master-design.md`.

- Generate the finished part and test pieces from the master script; share functions and parameters for critical interfaces.
- Preserve native scripts, parameters, dependency versions, originals and export hashes.
- Associate STL, STEP, GLB and 3MF exports with the current inputs. CAD uses millimeters; verify meter conversions for GLB/Blender separately.
- A build123d candidate can pass through STEP into the existing CadQuery export path. Freeze the STEP and input parameters; check dimensions and volume before and after conversion.
- Check minimum walls, watertightness, connected components, overlap, insertion/removal paths and required clearance. A zero contact distance still requires an intersection-volume check.
- The current build script supports cadquery/blender. Native Text-to-CAD viewing and export come from its independently installed plugin.

The current project owner integrates final versions. Keep candidates at separate paths and preserve previous versions and user choices. A version change invalidates checks for affected geometry.
