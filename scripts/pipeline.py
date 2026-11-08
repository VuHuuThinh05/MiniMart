"""Compatibility entry point: all new publications use DW ETL."""
import sys
from etl import run_pipeline
if __name__=='__main__':run_pipeline(force='--refresh-only' in sys.argv)
