# Bundled Grasshopper templates

Each entry in `manifest.json` should ship a sibling `.gh` file. Because
Grasshopper's binary format can only be authored from a live Rhino +
Grasshopper environment, the binaries are not committed by Claude Code.

The `gh_template_list` tool reads `manifest.json` and reports
`{name, description, parameters, available}` per entry, where `available`
is true only when the corresponding `.gh` file exists alongside this
manifest. To populate a template, open a fresh Grasshopper canvas, build
the parameter graph described under `description`, expose the listed
sliders/panels with their `name`s, save as `<name>.gh` here.

This separation keeps the catalogue contract independent of the binary
authoring step — automation (CI artefact upload, manual save, etc.) can
fill the binaries later without changing the Python contract.
