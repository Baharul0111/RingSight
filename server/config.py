"""Environment-only configuration. Never log this object or its values."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv(override=True)

@dataclass(frozen=True)
class Settings:
    redis_url: str = os.getenv('RS_TEST_REDIS_URL') or os.getenv('REDIS_URL','redis://localhost:6379')
    graph_name: str = os.getenv('GRAPH_NAME','rs_bank_a')
    planner: str = os.getenv('MODEL_PLANNER','claude-sonnet-5-5')
    judge: str = os.getenv('MODEL_JUDGE','claude-sonnet-5-5')
    narrative: str = os.getenv('MODEL_NARRATIVE','claude-opus-5-5')
    probe: str = os.getenv('MODEL_PROBE','claude-haiku-5-5')
    daily_cap: float = min(float(os.getenv('DAILY_USD_CAP','8')),8.0)
    accounts: int = int(os.getenv('ACCOUNTS','25000'))
    public_url: str = os.getenv('PUBLIC_URL','').rstrip('/')
    env: str = os.getenv('ENV','demo')
settings=Settings()
