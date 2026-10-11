# HACS and GitHub releases

[Deutsch](Releases.md) · **English**

This guide covers packaging and publishing. See [installation](Installation.en.md)
for user setup and [development](Development.en.md) for local tests.

## Initial preparation

Commit the project, including `.github/workflows/release.yml`, `hacs.json`,
`package-lock.json` and `custom_components/`, to the default branch of the public
`topic2k/EnigmaHAcompanion` repository. Enable GitHub Actions. The release job uses
the workflow's `contents: write` permission; no extra token or secret is needed.
Organization, branch and tag rules must permit the version commit and release
tag. The workflow stops when blocked and does not bypass these rules.

HACS detects `custom_components/enigmaha_companion/`. `hacs.json` selects
`zip_release: true` with the fixed asset name `enigmaha_companion.zip`. Its files
are at the ZIP root because HACS extracts it into the integration directory.
The versioned manual-install ZIP includes `custom_components/enigmaha_companion/`.
Both contain the same complete integration, shared protocol, German and English
translations, and logo. Entity icons come from the installed HA frontend at
runtime; no MDI catalog is shipped.

## Start a release

1. Commit and push the changes. You do not need to increase the version manually.
2. Open **GitHub → Actions → Release → Run workflow**.
3. Select the branch and automatic version increment: `patch` (default), `minor`
   or `major`. Optionally enter an explicit version such as `1.0.3` or `1.1.0`;
   this overrides the increment. Optionally enable prerelease publishing.
4. Choose **Run workflow**.

Automatic versioning uses the highest version from `package.json` and existing
`vMAJOR.MINOR.PATCH` release tags. Starting at `1.0.2`, patch gives `1.0.3`, minor
`1.1.0` and major `2.0.0`. Minor resets patch; major resets minor and patch.
The maintainer selects the increment; the workflow does not classify changes.

An explicit version must be at least the project version and higher than every
existing release tag.
Only `MAJOR.MINOR.PATCH` without `v` or suffix is accepted. The prerelease checkbox
sets GitHub/HACS's beta flag and also requires a new version number.

The workflow synchronizes `package.json`, both `package-lock.json` version fields,
the HA manifest, `const.py` and the shared component version in
`protocol/enigmaha_protocol/compatibility.py`, then builds packages and runs Python/frontend
tests. Only then does the separate release job receive write permissions. It
checks SHA256 sums and the tested source tree, creates `Release <Version>`, and
updates the chosen branch and `v<Version>` tag together. If the branch changed
during the build, it stops; rerun against the updated branch. Afterwards, update
the local branch with `git pull --ff-only`.

Assets are first uploaded to a draft. The release is published only after all
uploads succeed. Existing tags/releases are not overwritten. Prereleases are
not marked Latest.

| File | Purpose |
| --- | --- |
| `enigmaha_companion.zip` | HACS installation and updates |
| `enigmaha-companion-ha-<Version>.zip` | Manual HA installation |
| `enigma2-plugin-extensions-enigmahacompanion_<Version>_all.ipk` | OpenATV receiver |
| `enigmaha-companion-enigma2-<Version>.tar.gz` | Alternative receiver installation |
| `SHA256SUMS.txt` | Checksums for the four packages |

Users add the repository once as a HACS custom **Integration** and install a
published release. The development branch is hidden because
the build bundles the shared protocol. Enable beta versions in HACS to see
prereleases. Inclusion in HACS's default catalog is a separate process.

## Troubleshooting

- **Run workflow missing:** The workflow file must be on the default branch;
  starting a run requires repository write access.
- **Invalid or low version:** Use `MAJOR.MINOR.PATCH` above existing tags, or
  leave the explicit version empty.
- **Branch changed during build:** Rerun the workflow.
- **Tag/release already exists:** Increase the version. After a failed publish,
  inspect any remaining draft under Releases. Clean up only a confirmed
  unpublished failed attempt; leave published tags and packages unchanged. If the commit
  and tag were already written, the number is reserved and the next automatic run
  chooses the next number.
- **403 publishing:** Check Actions/repository policies for `GITHUB_TOKEN` and
  `contents: write`.
- **HACS cannot find the package:** Check public repository access, a published
  release and `enigmaha_companion.zip`. GitHub-generated source archives lack the
  protocol module added by the build.

## Release notes

The coordinated HACS/IPK workflow offers published stable releases only. The
HACS ZIP, IPK and `SHA256SUMS.txt` must use the names above in the same release.
Keep published assets and checksums unchanged: a started transaction pins its
receivers and target version. Both components must first be installed with the
update feature before the coordinated workflow becomes available.

Revise the automatically generated release notes after the workflow completes.
Describe user-visible changes first, followed by a brief account of other changes
without extensive technical detail. Include requirements, known issues and
limitations that affect usage. Do not include reports of executed tests, test
results or links to test reports. Store update and functional test reports only
under `.work/` and do not publish them.

The project is published. Consider backward compatibility with published versions
and provide required migrations. Briefly describe migrations and any necessary
reconfiguration in the release notes. Do not delete existing user data without
authorization. Continue installing the HA integration and receiver plugin from
the same release.

References: [HACS integration structure](https://www.hacs.xyz/docs/publish/integration/),
[HACS release ZIPs](https://www.hacs.xyz/docs/publish/start/),
[manual workflow runs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
