# Version Tagging System

This repository enforces semantic versioning with **mandatory git tags before every push**. All codebase edits must be tagged to maintain a clear version history.

## Versioning Scheme

The project uses **semantic versioning** with two formats:

- **Major Release**: `vX.Y` (e.g., `v3.5`, `v4.0`)
- **Minor/Patch Release**: `vX.Y.Z` (e.g., `v3.4.1`, `v3.4.2`)

### When to Use Each

- **Minor edits** (bug fixes, small improvements, documentation): Use `vX.Y.Z` format
  - Example: `v3.4` → `v3.4.1` → `v3.4.2`
- **New versions** (major features, breaking changes, new major release): Use `vX.Y` format
  - Example: `v3.4` → `v4.0`

## Quick Start

### Check Current Version
```bash
./version.sh current
```
Output shows the latest version, creation date, and commit hash.

### Create a Minor Tag (Bug Fix or Small Change)
```bash
./version.sh minor
```
- Increments the patch level: `v3.4` → `v3.4.1` or `v3.4.1` → `v3.4.2`
- Automatically tags HEAD commit
- Ready to push to origin

### Create a Major Tag (New Release)
```bash
./version.sh major
```
- Increments major version: `v3.4` → `v4.0`
- Automatically tags HEAD commit
- Ready to push to origin

### View All Versions
```bash
./version.sh list
```
Shows all version tags with creation dates and commit hashes.

### Rollback to a Previous Version
```bash
./version.sh rollback v3.1
```
- Checks out the specific version's commit
- Places you in detached HEAD state
- Use `git checkout -b branch-name` to create a new branch from that point

### Get Help
```bash
./version.sh help
```

## Enforcement: Pre-Push Hook

A **pre-push hook** is automatically installed at `.git/hooks/pre-push`. This hook:

1. **Blocks all pushes** unless the current HEAD commit has a version tag
2. **Shows helpful guidance** when a tag is missing:
   - Current version number
   - Suggested next versions
   - Commands to create and push tags

### Testing the Hook

To verify the hook is working, try pushing without a tag:

```bash
git commit --allow-empty -m "Test commit without tag"
git push origin HEAD:test-branch
```

You should see an error:
```
ERROR: Version tag required before push

Every commit must be tagged with a semantic version before pushing.

Current version: v3.4

Suggested next versions:
  - Minor edit (v3.4.X): Use './version.sh minor'
  - Major release (v4.0): Use './version.sh major'
```

## Workflow

### Standard Development Workflow

1. **Make your changes**:
   ```bash
   git add .
   git commit -m "Your commit message"
   ```

2. **Create a version tag** for your commit:
   ```bash
   # For small changes/bug fixes
   ./version.sh minor

   # For new features/major releases
   ./version.sh major
   ```

3. **Push to origin**:
   ```bash
   git push origin main v3.4.1  # includes both commits and tag
   ```

### Alternative: Manual Tagging

If you prefer manual tagging:

```bash
# Create and annotate a tag
git tag -a v3.4.1 -m "Version 3.4.1 - Bug fixes"

# Push the tag
git push origin v3.4.1
```

## Tag Naming Conventions

- All tags MUST start with `v` (lowercase)
- Valid formats: `v1.0`, `v1.0.0`, `v2.3.4`
- Invalid formats: `V1.0`, `1.0`, `version-1.0`, `release-1.0`

## Version History

To see all versions with dates and commit info:

```bash
./version.sh list
```

Example output:
```
Version History:

  v3.4       2026-02-15  a5ae1a5c1234567890abcdef1234567890abcdef
    v3.4: Knowledge Harvester — active extraction daemon

  v3.3       2026-02-10  fd1f93d7890abcdef1234567890abcdef123456
    v3.3: Infrastructure improvements and cleanup

  v3.2       2026-02-05  1775867890abcdef1234567890abcdef1234567
    v3.2: Bug fixes and optimizations
```

## FAQ

**Q: Can I push without a tag?**
A: No. The pre-push hook blocks all pushes without version tags. This is intentional to maintain a clear version history.

**Q: What if I forgot to tag before committing?**
A: No problem! Tag your current HEAD and push:
```bash
./version.sh minor
git push origin v3.4.1
```

**Q: Can I delete a tag?**
A: Yes, but be careful:
```bash
git tag -d v3.4.1          # Delete local tag
git push origin :v3.4.1    # Delete remote tag
```

**Q: What's the difference between major and minor?**
A:
- **Minor**: `v3.4` → `v3.4.1` (patch level increment)
- **Major**: `v3.4` → `v4.0` (next major version)

**Q: Can I tag an old commit?**
A: Yes:
```bash
git tag -a v3.4 <commit-hash> -m "Tagging old commit"
git push origin v3.4
```

## Technical Details

### Pre-Push Hook Location
The hook is at: `.git/hooks/pre-push`

It checks:
- If the current HEAD commit has a version tag (format: `v[0-9]*`)
- If not, displays helpful error messages and blocks the push

### Version Script Location
The helper script is at: `./version.sh`

It provides:
- Version checking and listing
- Automated version incrementing
- Tag creation with proper annotations
- Rollback capability

Both are **executable** and require no additional setup beyond running `./version.sh`.

## Initialization (First Time)

If this is a brand new project with no tags:

```bash
./version.sh major    # Creates v1.0
git push origin v1.0
```

Then for all subsequent changes:
```bash
./version.sh minor    # v1.0 → v1.0.1
# or
./version.sh major    # v1.0 → v2.0
```

---

**Note**: Version tagging enforcement is HARDCODED and non-optional. Every push requires a version tag.
