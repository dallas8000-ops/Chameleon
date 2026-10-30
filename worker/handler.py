"""RunPod Serverless entry point. Run `python handler.py --test_input '{...}'` to try a job locally."""
import runpod

from chameleon_worker.router import handle

if __name__ == "__main__":
    runpod.serverless.start({"handler": handle})
