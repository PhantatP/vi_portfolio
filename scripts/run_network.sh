#!/bin/bash
# scripts/run_network.sh
# usage: bash scripts/run_network.sh

# Ensure we are in the project root
cd "$(dirname "$0")/.."

# Activate venv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run Streamlit on 0.0.0.0 to allow network access
echo "🚀 Starting VI Portfolio on 0.0.0.0:8501"
echo "👉 Access from other devices via http://<THIS_DEVICE_IP>:8501"
streamlit run app/web_app.py --server.address=0.0.0.0
