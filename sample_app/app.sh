#!/bin/sh
echo "======================================"
echo " Docksmith Sample App v${APP_VERSION}"
echo "======================================"
echo ""
echo "${GREETING} from inside the container!"
echo ""
echo "Environment variables:"
env | sort
echo ""
echo "Working directory: $(pwd)"
echo ""
echo "Done. Exiting cleanly."
# changed
# changed
