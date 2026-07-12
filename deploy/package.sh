#!/bin/bash
set -e

echo "Building deployment package..."

# Create clean staging directory
rm -rf ./.deploy_build
mkdir -p ./.deploy_build

# Copy necessary files and directories
cp -r src ./.deploy_build/
cp -r templates ./.deploy_build/
cp -r data ./.deploy_build/
# never ship local runtime stores — user password hashes & per-user profiles
# live only on the running instance's /tmp (see s.yaml env), never in the bundle
rm -f ./.deploy_build/data/*.local.json
rm -rf ./.deploy_build/data/profiles.local
cp s.yaml ./.deploy_build/
cp bootstrap ./.deploy_build/
cp deploy/requirements.txt ./.deploy_build/

# Install dependencies into vendor directory
cd ./.deploy_build
python3 -m pip install -r requirements.txt -t vendor --platform manylinux2014_x86_64 --python-version 311 --only-binary=:all:

# Make bootstrap executable
chmod +x bootstrap

echo "Deployment package built successfully in ./.deploy_build/"
echo "Next steps:"
echo "  cd .deploy_build"
echo "  s deploy"
