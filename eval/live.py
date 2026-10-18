"""Verify the public API on Erlan's 30 synthetic scenarios; no API keys needed."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import time

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT
from backend.schemas import RecommendResponse


def grounded_ids(answer, local_ids):
    if answer.source == 'local':
        return local_ids
    # Remote catalogue IDs are not expected in the static OSM snapshot.
    eligible = {p.poi_id for p in answer.nearby_places if p.eligible}
    return {c.poi_id for c in answer.candidates if not c.excluded_because
            and c.poi_id in eligible and c.poi_id.startswith('2gis_')}


async def run(args):
    source = json.loads((ROOT / 'eval/scenarios_spec.json').read_text(encoding='utf-8'))
    allowed = {p['poi_id'] for p in json.loads((ROOT / 'data/poi.json').read_text(encoding='utf-8'))}
    out = Path(args.output)
    (out / 'answers').mkdir(parents=True, exist_ok=True)
    rows = []
    async with httpx.AsyncClient(base_url=args.url.rstrip('/'), timeout=90) as client:
        health = (await client.get('/health')).raise_for_status().json()
        for group in source['scenarios']:
            for n, query in enumerate(group['queries'][:args.per_scenario], 1):
                ctx = {k: v for k, v in group['context'].items() if k != 'airport_buffer_min'}
                ctx['simulate'] = True
                req = {'query': query['text'], 'context': ctx, 'source': args.source,
                       'location': {k: v for k, v in group['location'].items() if k != 'preset'}}
                started = time.perf_counter()
                response = await client.post('/recommend', json=req)
                response.raise_for_status()
                answer = RecommendResponse.model_validate(response.json())
                elapsed = (time.perf_counter() - started) * 1000
                cards, expected, issues = answer.recommendations, group['expected'], []
                grounded = grounded_ids(answer, allowed)
                if not expected['min_places'] <= len(cards) <= expected['max_places']:
                    issues.append('card_count')
                if expected.get('must_have_safety_note') and not answer.safety:
                    issues.append('safety_note')
                if answer.considered.radius_m > expected.get('max_radius_m', float('inf')):
                    issues.append('radius')
                for c in cards:
                    if c.poi_id not in grounded:
                        issues.append('invented_id')
                    if c.category not in expected['categories_allowed'] or c.category in expected['categories_forbidden']:
                        issues.append('category')
                    if c.walk_min > expected['max_walk_min']:
                        issues.append('walk_limit')
                    b = c.budget_breakdown
                    if b.total_min > answer.considered.time_budget_min:
                        issues.append('budget')
                    if b.total_min - b.reserve_min > expected.get('max_total_min', float('inf')):
                        issues.append('visit_budget')
                    if c.open_status.state == 'closed':
                        issues.append('closed')
                    if c.open_status.state == 'open' and (not c.open_status.hours or c.open_status.source == 'none'):
                        issues.append('unsupported_open')
                    if not c.why or not c.what_to_do or c.time_to_spend_min <= 0:
                        issues.append('four_parts')
                case = f"{group['id']}.{n}"
                (out / 'answers' / f'{case}.json').write_text(answer.model_dump_json(indent=2)+'\n', encoding='utf-8')
                cached_start = time.perf_counter()
                repeated = (await client.post('/recommend', json=req)).raise_for_status().json()
                cached_ms = (time.perf_counter()-cached_start)*1000
                row = dict(id=case, source=answer.source, source_error=answer.source_error,
                           mode=answer.mode, cards=len(cards), issues=sorted(set(issues)),
                           elapsed_ms=round(elapsed, 1), cached_mode=repeated['mode'], cached_ms=round(cached_ms,1))
                rows.append(row)
                print(json.dumps(row), flush=True)
                (out/'progress.json').write_text(json.dumps(rows,indent=2)+'\n')
                # At most two uncached Gemini calls per request; keep below 15 calls/minute.
                await asyncio.sleep(max(0, args.interval-(time.perf_counter()-started)))
        cors = await client.options('/recommend', headers={'Origin':'https://seruen-astana.netlify.app',
            'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Content-Type'})
        disabled = await client.get('/places/'+next(iter(allowed))+'/details')
    report = dict(checked_at=datetime.now(timezone.utc).isoformat(), url=args.url, health=health,
        source='eval/scenarios_spec.json', requested_source=args.source,
        queries=len(rows), passed=sum(not x['issues'] for x in rows),
        modes=dict(Counter(x['mode'] for x in rows)), mean_ms=round(statistics.mean(x['elapsed_ms'] for x in rows),1),
        max_ms=max(x['elapsed_ms'] for x in rows), mean_cached_ms=round(statistics.mean(x['cached_ms'] for x in rows),1),
        max_cached_ms=max(x['cached_ms'] for x in rows),
        cached_within_1s=sum(x['cached_ms'] < 1000 for x in rows),
        cached_count=sum(x['cached_mode']=='cached' for x in rows), cases=rows,
        cors_origin=cors.headers.get('access-control-allow-origin'), places_status=disabled.status_code,
        manual_mean=None, notes=['Synthetic scenario locations only. Human relevance scores are still required.',
            'Latency includes network; mode=ai is counted only when the public response actually says ai.',
            'Intent correctness of the live Gemini JSON is not exposed and is not inferred from card counts.'])
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'},ensure_ascii=False,indent=2))
    if report['passed']!=report['queries']:
        raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='https://seruen-backend-f36d.onrender.com')
    parser.add_argument('--output',default=str(ROOT/'eval/live'))
    parser.add_argument('--interval',type=float,default=18)
    parser.add_argument('--source',choices=['local', '2gis', 'auto'],default='local')
    parser.add_argument('--per-scenario',type=int,choices=range(1,6),default=5)
    asyncio.run(run(parser.parse_args()))
