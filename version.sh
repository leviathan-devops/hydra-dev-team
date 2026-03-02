#!/bin/bash

# Version.sh - Helper script for semantic versioning
# Manages git version tags with automated incrementing

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Validate semver format
validate_version() {
    local version=$1
    if ! [[ $version =~ ^v[0-9]+\.[0-9]+(\.[0-9]+)?$ ]]; then
        echo -e "${RED}ERROR: Invalid version format: $version${NC}"
        echo "Expected format: vX.Y or vX.Y.Z"
        exit 1
    fi
}

# Get current version (latest tag)
get_current_version() {
    local tag=$(git tag -l 'v*' --sort=-version:refname | head -1)
    if [ -z "$tag" ]; then
        echo "none"
    else
        echo "$tag"
    fi
}

# Increment minor version (patch level)
increment_minor() {
    local current=$1
    # Remove 'v' prefix
    current=${current#v}

    # Count dots to determine if we have major.minor or major.minor.patch
    local dot_count=$(echo "$current" | tr -cd '.' | wc -c)

    if [ $dot_count -eq 1 ]; then
        # Format: major.minor -> major.minor.1
        echo "v${current}.1"
    else
        # Format: major.minor.patch -> major.minor.(patch+1)
        local major_minor=${current%.*}
        local patch=${current##*.}
        echo "v${major_minor}.$((patch + 1))"
    fi
}

# Increment major version
increment_major() {
    local current=$1
    # Remove 'v' prefix
    current=${current#v}

    # Count dots to determine if we have major.minor or major.minor.patch
    local dot_count=$(echo "$current" | tr -cd '.' | wc -c)

    if [ $dot_count -eq 1 ]; then
        # Format: major.minor -> (major+1).0
        local major=${current%%.*}
        echo "v$((major + 1)).0"
    else
        # Format: major.minor.patch -> (major+1).0
        local major=${current%%.*}
        echo "v$((major + 1)).0"
    fi
}

# Command: current
cmd_current() {
    local version=$(get_current_version)
    if [ "$version" = "none" ]; then
        echo -e "${YELLOW}No version tags found${NC}"
        exit 0
    fi

    local commit=$(git rev-list -n 1 "$version" 2>/dev/null)
    local date=$(git log -1 --format=%ai "$version" 2>/dev/null | cut -d' ' -f1)

    echo -e "${BLUE}Current version: ${GREEN}${version}${NC}"
    echo "Created: $date"
    echo "Commit:  $commit"
}

# Command: minor
cmd_minor() {
    local current=$(get_current_version)

    if [ "$current" = "none" ]; then
        echo -e "${RED}ERROR: No current version found. Initialize with './version.sh major'${NC}"
        exit 1
    fi

    local next=$(increment_minor "$current")
    validate_version "$next"

    echo -e "${YELLOW}Creating minor version${NC}"
    echo "  Current: ${GREEN}${current}${NC}"
    echo "  Next:    ${GREEN}${next}${NC}"

    # Check if tag already exists
    if git rev-parse "$next" >/dev/null 2>&1; then
        echo -e "${RED}ERROR: Tag '$next' already exists${NC}"
        exit 1
    fi

    # Create the tag
    git tag -a "$next" -m "Version $next - Minor release"
    echo -e "${GREEN}✓ Tagged HEAD as $next${NC}"
    echo ""
    echo "To push this tag:"
    echo "  git push origin $next"
}

# Command: major
cmd_major() {
    local current=$(get_current_version)

    if [ "$current" = "none" ]; then
        # First release
        local next="v1.0"
    else
        local next=$(increment_major "$current")
    fi

    validate_version "$next"

    echo -e "${YELLOW}Creating major version${NC}"
    if [ "$current" != "none" ]; then
        echo "  Current: ${GREEN}${current}${NC}"
    fi
    echo "  Next:    ${GREEN}${next}${NC}"

    # Check if tag already exists
    if git rev-parse "$next" >/dev/null 2>&1; then
        echo -e "${RED}ERROR: Tag '$next' already exists${NC}"
        exit 1
    fi

    # Create the tag
    git tag -a "$next" -m "Version $next - Major release"
    echo -e "${GREEN}✓ Tagged HEAD as $next${NC}"
    echo ""
    echo "To push this tag:"
    echo "  git push origin $next"
}

# Command: list
cmd_list() {
    local tags=$(git tag -l 'v*' --sort=-version:refname)

    if [ -z "$tags" ]; then
        echo -e "${YELLOW}No version tags found${NC}"
        exit 0
    fi

    echo -e "${BLUE}Version History:${NC}"
    echo ""

    while IFS= read -r tag; do
        local commit=$(git rev-list -n 1 "$tag" 2>/dev/null)
        local date=$(git log -1 --format=%ai "$tag" 2>/dev/null | cut -d' ' -f1)
        local message=$(git tag -l "$tag" -n1 --format='%(refname:short): %(contents:subject)' | sed 's/^[^:]*: //')

        printf "  ${GREEN}%-10s${NC} %s  %s\n" "$tag" "$date" "$commit"
        printf "    %s\n" "$message"
        echo ""
    done <<< "$tags"
}

# Command: rollback
cmd_rollback() {
    local target_version=$1

    if [ -z "$target_version" ]; then
        echo -e "${RED}ERROR: Please specify a version to rollback to${NC}"
        echo "Usage: ./version.sh rollback v3.1"
        exit 1
    fi

    validate_version "$target_version"

    # Check if tag exists
    if ! git rev-parse "$target_version" >/dev/null 2>&1; then
        echo -e "${RED}ERROR: Version tag '$target_version' does not exist${NC}"
        exit 1
    fi

    echo -e "${YELLOW}Rolling back to $target_version${NC}"
    local commit=$(git rev-list -n 1 "$target_version")
    echo "Checking out commit: $commit"

    git checkout "$commit"

    echo -e "${GREEN}✓ Checked out $target_version${NC}"
    echo ""
    echo "WARNING: You are in detached HEAD state."
    echo "To create a new branch from this version:"
    echo "  git checkout -b new-branch-name"
}

# Show usage
show_usage() {
    cat <<EOF
${BLUE}Version Helper Script${NC}

Usage: ./version.sh <command> [options]

Commands:
  ${GREEN}current${NC}              Show current version
  ${GREEN}minor${NC}               Create next minor version (patch increment)
  ${GREEN}major${NC}               Create next major version
  ${GREEN}list${NC}                List all version tags with dates
  ${GREEN}rollback <version>${NC}  Checkout a specific version tag
  ${GREEN}help${NC}                Show this help message

Version Format:
  Major: vX.Y (e.g., v3.5)
  Minor: vX.Y.Z (e.g., v3.4.1)

Examples:
  ./version.sh current        # Show current version
  ./version.sh minor          # v3.4 → v3.4.1
  ./version.sh major          # v3.4 → v3.5
  ./version.sh list           # Show all versions
  ./version.sh rollback v3.1  # Go back to v3.1

EOF
}

# Main script logic
main() {
    local command=$1

    case "$command" in
        current)
            cmd_current
            ;;
        minor)
            cmd_minor
            ;;
        major)
            cmd_major
            ;;
        list)
            cmd_list
            ;;
        rollback)
            cmd_rollback "$2"
            ;;
        help|--help|-h|"")
            show_usage
            ;;
        *)
            echo -e "${RED}Unknown command: $command${NC}"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

main "$@"
