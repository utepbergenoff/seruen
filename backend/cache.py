import hashlib
import json
import time
from collections import OrderedDict


class ResponseCache:
    """Only opaque hashes and response cards; never stores raw queries/user locations."""

    def __init__(self, size=256):
        self.size = size
        self.entries = OrderedDict()

    def key(self, request, target, fingerprint, variant):
        body = request.model_dump(mode="json")
        body.pop("request_id", None)
        # Timestamp slot and all context affect the key; nearby users cannot share raw coordinates.
        body["context"]["now"] = None
        body["query"] = " ".join(request.query.casefold().split())
        body.update(slot=int(target.timestamp() // 1800), data=fingerprint, variant=variant)
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def get(self, key):
        entry = self.entries.get(key)
        if entry is None:
            return None
        expires, response = entry
        if time.monotonic() >= expires:
            self.entries.pop(key)
            return None
        self.entries.move_to_end(key)
        return response.model_copy(deep=True)

    def put(self, key, response, ttl):
        self.entries[key] = (time.monotonic() + max(0, ttl), response.model_copy(deep=True))
        self.entries.move_to_end(key)
        while len(self.entries) > self.size:
            self.entries.popitem(last=False)
