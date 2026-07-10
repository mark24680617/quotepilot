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
cp s.yaml ./.deploy_build/
cp bootstrap ./.deploy_build/
cp deploy/requirements.txt ./.deploy_build/

# Install dependencies into vendor directory
cd ./.deploy_build
python3 -m pip install -r requirements.txt -t vendor --platform manylinux2014_x86_64 --python-version 310 --only-binary=:all:

# Make bootstrap executable
chmod +x bootstrap

echo "Deployment package built successfully in ./.deploy_build/"
echo "Next steps:"
echo "  cd .deploy_build"
echo "  s deploy"
