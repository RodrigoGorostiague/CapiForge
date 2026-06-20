# Launchpad PPA staging checklist

Use this checklist before promoting a CapiForge build from staging to a stable PPA.

## Prerequisites

- Ubuntu 24.04 (noble) build host or container with build dependencies from `debian/README.Debian`
- GPG key enrolled in Launchpad with signing subkey available locally
- Launchpad PPA created (for example `ppa:USER/capiforge-staging`)
- `dput` configured with the correct PPA target

## Build and local smoke test

1. From a clean checkout, run `./scripts/build-deb.sh` and confirm a `.deb` is produced in the parent directory.
2. Run lintian on the generated `.changes` file (warn-only is acceptable initially).
3. Run the packaging integration test:
   ```bash
   python3 -m unittest tests.packaging.deb_integration_test -v
   ```
4. Optionally install the `.deb` on a disposable noble VM:
   ```bash
   sudo dpkg -i ../capiforge_*_all.deb
   sudo apt-get install -f
   capiforge --version
   capinstall --no-tui-ui verify --json
   ```

## Source upload to staging PPA

1. Bump `debian/changelog` with the release version and target PPA.
2. Build source package:
   ```bash
   debuild -S -sa
   ```
3. Sign the source if required by your Launchpad workflow.
4. Upload to staging:
   ```bash
   dput ppa:USER/capiforge-staging ../capiforge_*_source.changes
   ```
5. Wait for Launchpad builders to finish on noble (and jammy if enabled).

## Post-upload validation

1. Add the staging PPA on a clean noble machine:
   ```bash
   sudo add-apt-repository ppa:USER/capiforge-staging
   sudo apt update
   sudo apt install capiforge
   ```
2. In a fresh git repository, run:
   ```bash
   capiforge init --non-interactive
   capiforge adopt --non-interactive
   capinstall --no-tui-ui verify --json
   ```
3. Confirm share data resolves from `/usr/share/capiforge` without `CAPIFORGE_SHARE`.
4. Confirm TUI launches when `python3-textual` is present.

## Promotion gate

- [ ] CI `deb-build` workflow green on the release tag
- [ ] Integration test passes locally or in CI
- [ ] Staging `apt install` smoke test passes on noble
- [ ] README PPA install instructions match the staging PPA name
- [ ] Known jammy Textual dependency gap documented if jammy builds are enabled

After staging validation, copy or promote the same source upload to the stable PPA (`ppa:USER/capiforge`) and update README links accordingly.
