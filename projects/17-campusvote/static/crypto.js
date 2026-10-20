/* CampusVote client-side crypto: SHA-256, HMAC, RSA blind signatures, commitments,
 * RSA-KEM sealing and a full bulletin-board audit - all from scratch on JS BigInt.
 * Mirrors campusvote/*.py byte for byte. Works without crypto.subtle (plain-HTTP LAN).
 */
(function (root) {
  'use strict';

  // ---------------------------------------------------------------- bytes
  const enc = new TextEncoder();
  const utf8 = (s) => enc.encode(s);
  function concat(...parts) {
    let n = 0;
    for (const p of parts) n += p.length;
    const out = new Uint8Array(n);
    let o = 0;
    for (const p of parts) { out.set(p, o); o += p.length; }
    return out;
  }
  function toHex(bytes) {
    let s = '';
    for (let i = 0; i < bytes.length; i++) s += (bytes[i] < 16 ? '0' : '') + bytes[i].toString(16);
    return s;
  }
  function fromHex(h) {
    const out = new Uint8Array(h.length >> 1);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(h.substr(2 * i, 2), 16);
    return out;
  }
  function u32be(i) { return new Uint8Array([(i >>> 24) & 255, (i >>> 16) & 255, (i >>> 8) & 255, i & 255]); }

  // ---------------------------------------------------------------- SHA-256 (FIPS 180-4)
  const K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);
  const W = new Uint32Array(64);
  function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }
  function sha256(bytes) {
    const len = bytes.length;
    const total = ((len + 9 + 63) >> 6) << 6;
    const p = new Uint8Array(total);
    p.set(bytes);
    p[len] = 0x80;
    const dv = new DataView(p.buffer);
    dv.setUint32(total - 8, Math.floor(len / 0x20000000));
    dv.setUint32(total - 4, (len << 3) >>> 0);
    let h0 = 0x6a09e667, h1 = 0xbb67ae85, h2 = 0x3c6ef372, h3 = 0xa54ff53a,
      h4 = 0x510e527f, h5 = 0x9b05688c, h6 = 0x1f83d9ab, h7 = 0x5be0cd19;
    for (let off = 0; off < total; off += 64) {
      for (let i = 0; i < 16; i++) W[i] = dv.getUint32(off + 4 * i);
      for (let i = 16; i < 64; i++) {
        const a = W[i - 15], b = W[i - 2];
        const s0 = rotr(a, 7) ^ rotr(a, 18) ^ (a >>> 3);
        const s1 = rotr(b, 17) ^ rotr(b, 19) ^ (b >>> 10);
        W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
      }
      let a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;
      for (let i = 0; i < 64; i++) {
        const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        const ch = (e & f) ^ (~e & g);
        const t1 = (h + S1 + ch + K[i] + W[i]) >>> 0;
        const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        const maj = (a & b) ^ (a & c) ^ (b & c);
        const t2 = (S0 + maj) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      h0 = (h0 + a) >>> 0; h1 = (h1 + b) >>> 0; h2 = (h2 + c) >>> 0; h3 = (h3 + d) >>> 0;
      h4 = (h4 + e) >>> 0; h5 = (h5 + f) >>> 0; h6 = (h6 + g) >>> 0; h7 = (h7 + h) >>> 0;
    }
    const out = new Uint8Array(32);
    const odv = new DataView(out.buffer);
    [h0, h1, h2, h3, h4, h5, h6, h7].forEach((v, i) => odv.setUint32(4 * i, v));
    return out;
  }
  const sha256hex = (x) => toHex(sha256(typeof x === 'string' ? utf8(x) : x));

  function hmac(key, msg) {
    if (key.length > 64) key = sha256(key);
    const k = new Uint8Array(64);
    k.set(key);
    const ip = k.map((b) => b ^ 0x36), op = k.map((b) => b ^ 0x5c);
    return sha256(concat(op, sha256(concat(ip, msg))));
  }

  // ---------------------------------------------------------------- BigInt maths
  const big = (h) => BigInt('0x' + (h || '0'));
  const bigHex = (x, len) => (len ? x.toString(16).padStart(2 * len, '0') : x.toString(16));
  const bigBytes = (x, len) => fromHex(bigHex(x, len));
  const bitLength = (x) => (x === 0n ? 0 : x.toString(2).length);
  const byteLength = (x) => Math.ceil(bitLength(x) / 8);
  function modPow(b, e, m) {
    let r = 1n;
    b %= m;
    while (e > 0n) {
      if (e & 1n) r = (r * b) % m;
      b = (b * b) % m;
      e >>= 1n;
    }
    return r;
  }
  function gcd(a, b) { while (b) { [a, b] = [b, a % b]; } return a; }
  function modInv(a, m) {               // iterative extended Euclid
    let [r0, r1] = [((a % m) + m) % m, m], [x0, x1] = [1n, 0n];
    while (r1) {
      const q = r0 / r1;
      [r0, r1] = [r1, r0 - q * r1];
      [x0, x1] = [x1, x0 - q * x1];
    }
    if (r0 !== 1n) throw new Error('not invertible');
    return ((x0 % m) + m) % m;
  }
  function randomBytes(n) {
    const out = new Uint8Array(n);
    (root.crypto || globalThis.crypto).getRandomValues(out);
    return out;
  }
  function randomBelow(n) {             // uniform in [0, n) by rejection sampling
    const bits = bitLength(n), len = Math.ceil(bits / 8), excess = BigInt(8 * len - bits);
    for (;;) {
      const x = big(toHex(randomBytes(len))) >> excess;
      if (x < n) return x;
    }
  }

  // ---------------------------------------------------------------- protocol
  const FDH_DOMAIN = utf8('CV1-FDH');
  function fdh(msg, n) {                // == campusvote.rsa.fdh
    const outbits = bitLength(n) - 1, k = Math.ceil(outbits / 8);
    const parts = [];
    let have = 0, ctr = 0;
    while (have < k) {
      const d = sha256(concat(FDH_DOMAIN, u32be(ctr), msg));
      parts.push(d); have += d.length; ctr++;
    }
    return big(toHex(concat(...parts).slice(0, k))) >> BigInt(8 * k - outbits);
  }
  const pubKey = (d) => ({ n: big(d.n), e: BigInt(d.e), size: byteLength(big(d.n)), fp: d.fp });
  const tokenMessage = (eid, token) => utf8('CV1-token|' + eid + '|' + token);
  const newSecretHex = () => toHex(randomBytes(32));

  function blind(pub, msg) {
    const m = fdh(msg, pub.n);
    let r;
    do { r = 2n + randomBelow(pub.n - 3n); } while (gcd(r, pub.n) !== 1n);
    return { m, r, blinded: (m * modPow(r, pub.e, pub.n)) % pub.n };
  }
  const unblind = (pub, blindSig, r) => (blindSig * modInv(r, pub.n)) % pub.n;
  const verifyToken = (pub, eid, token, sig) => sig > 0n && sig < pub.n &&
    modPow(sig, pub.e, pub.n) === fdh(tokenMessage(eid, token), pub.n);
  const verifyMessage = (pub, msg, sig) => sig > 0n && sig < pub.n &&
    modPow(sig, pub.e, pub.n) === fdh(utf8(msg), pub.n);

  function canonical(v) {               // == json.dumps(sort_keys=True, separators=(",", ":"))
    if (v === null || v === undefined) return 'null';
    if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
    if (typeof v === 'object') {
      return '{' + Object.keys(v).sort().map((k) => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}';
    }
    return JSON.stringify(v);
  }
  const commitBallot = (eid, token, choices, nonce) =>
    sha256hex('CV1-commit|' + eid + '|' + token + '|' + canonical(choices) + '|' + nonce);

  function keystream(kenc, len) {
    const parts = [];
    for (let i = 0, have = 0; have < len; i++) { parts.push(sha256(concat(kenc, u32be(i)))); have += 32; }
    return concat(...parts).slice(0, len);
  }
  function seal(pub, plaintext, aad) {  // == campusvote.seal.seal (RSA-KEM + SHA-256 CTR + HMAC)
    const r = 2n + randomBelow(pub.n - 3n);
    const c0hex = bigHex(modPow(r, pub.e, pub.n), pub.size);
    const Kk = sha256(concat(utf8('CV1-KEM'), bigBytes(r, pub.size)));
    const kenc = hmac(Kk, utf8('enc')), kmac = hmac(Kk, utf8('mac'));
    const ks = keystream(kenc, plaintext.length);
    const ct = plaintext.map((b, i) => b ^ ks[i]);
    const cthex = toHex(ct);
    return { c0: c0hex, ct: cthex, tag: toHex(hmac(kmac, utf8(aad + '|' + c0hex + '|' + cthex))) };
  }

  const entryHash = (e) => sha256hex(canonical({ seq: e.seq, type: e.type, time: e.time, data: e.data, prev: e.prev }));
  const checkpointMessage = (eid, upto, head, ballots) => 'CV1-checkpoint|' + eid + '|' + upto + '|' + head + '|' + ballots;
  function resultMessage(eid, data) {
    const body = {};
    Object.keys(data).forEach((k) => { if (k !== 'sig') body[k] = data[k]; });
    return 'CV1-result|' + eid + '|' + sha256hex(canonical(body));
  }

  // ---------------------------------------------------------------- full audit (== campusvote.audit)
  function audit(entries) {
    const t0 = performance.now();
    const steps = [];
    const step = (id, title, ok, detail) => steps.push({ id, title, ok, detail });
    const g = entries[0];
    if (!g || g.type !== 'genesis') {
      step('genesis', 'Genesis manifest and public keys', false, 'missing genesis entry');
      return { verdict: 'FAILED', steps, ms: performance.now() - t0 };
    }
    const man = g.data.election, eid = man.eid, eligible = g.data.roster.eligible;
    const issuer = pubKey(g.data.keys.issuer), boardKey = pubKey(g.data.keys.board);
    step('genesis', 'Genesis manifest and public keys', true,
      `Election ${eid}, ${man.posts.length} posts, ${eligible} eligible; issuer key ${g.data.keys.issuer.fp}`);

    // chain
    let prev = '0'.repeat(64), firstBreak = null, breakDetail = '';
    entries.forEach((e, i) => {
      let why = null;
      if (e.seq !== i) why = `sequence: expected #${i}, found #${e.seq}`;
      else if (e.prev !== prev) why = 'link: prev hash does not match the previous entry';
      else if (entryHash(e) !== e.hash) why = 'content: stored hash differs from the recomputed hash';
      if (why && firstBreak === null) { firstBreak = i; breakDetail = why; }
      prev = e.hash;
    });
    step('chain', 'Hash chain intact', firstBreak === null, firstBreak === null
      ? `${entries.length} entries recomputed in your browser; head ${prev.slice(0, 16)}...`
      : `BROKEN at entry #${firstBreak} (${breakDetail})`);

    const by = (t) => entries.filter((e) => e.type === t);
    const issu = by('issuance'), ballots = by('ballot'), cps = by('checkpoint'), opens = by('opening'), res = by('result');
    const prefix = [];
    let run = 0;
    entries.forEach((e) => { run += e.type === 'ballot' ? 1 : 0; prefix.push(run); });
    let badCp = 0;
    cps.forEach((c) => {
      const d = c.data, okHead = entries[d.upto] && entries[d.upto].hash === d.head && prefix[d.upto] === d.ballots;
      if (!okHead || !verifyMessage(boardKey, checkpointMessage(eid, d.upto, d.head, d.ballots), big(d.sig))) badCp++;
    });
    step('checkpoints', 'Signed checkpoints valid', badCp === 0 && cps.length > 0,
      badCp ? `${badCp} of ${cps.length} checkpoints FAIL (signature or pinned head)` : `${cps.length} RSA-signed checkpoints verify`);

    const ph = {};
    by('phase').forEach((e) => { if (!(e.data.phase in ph)) ph[e.data.phase] = e.seq; });
    const outside = ballots.filter((b) => ph.voting === undefined || b.seq < ph.voting || (ph.closed !== undefined && b.seq > ph.closed));
    step('phases', 'Ballots only inside the voting phase', outside.length === 0,
      outside.length ? `${outside.length} ballots outside the voting phase` : `all ${ballots.length} ballots inside`);

    const refs = new Set();
    let badIss = 0;
    issu.forEach((e) => {
      if (refs.has(e.data.voter_ref)) badIss++;
      refs.add(e.data.voter_ref);
      if (modPow(big(e.data.blind_sig), issuer.e, issuer.n) !== big(e.data.blinded)) badIss++;
    });
    step('issuance', 'One blind signature per eligible voter', badIss === 0 && issu.length <= eligible,
      `${issu.length} tokens to ${refs.size} voters of ${eligible}${badIss ? `, ${badIss} problems` : ', all well-formed'}`);

    let badSig = 0;
    const seen = new Map();
    let dups = 0;
    ballots.forEach((b) => {
      if (!verifyToken(issuer, eid, b.data.token, big(b.data.sig))) badSig++;
      if (seen.has(b.data.token)) dups++;
      seen.set(b.data.token, b);
    });
    step('signatures', 'Every ballot carries a valid authority signature', badSig === 0,
      badSig ? `${badSig} INVALID signatures` : `${ballots.length} / ${ballots.length} verify`);
    step('duplicates', 'No token used twice', dups === 0, dups ? `${dups} duplicates` : `${seen.size} distinct tokens`);
    step('counts', 'Ballots <= tokens issued <= eligible', ballots.length <= issu.length && issu.length <= eligible,
      `${ballots.length} ${ballots.length <= issu.length ? '<=' : '> (STUFFING)'} ${issu.length} <= ${eligible}`);

    let tally = null;
    if (ph.closed !== undefined) {
      const counts = {};
      man.posts.forEach((p) => { counts[p.id] = {}; p.candidates.forEach((c) => { counts[p.id][c.id] = 0; }); });
      let counted = 0, badOpen = 0, spoiled = 0;
      const byTok = new Map(opens.map((o) => [o.data.token, o]));
      seen.forEach((b, tok) => {
        const o = byTok.get(tok);
        if (!o) { badOpen++; return; }
        if (o.data.status !== 'ok') { spoiled++; return; }
        const ch = o.data.choices || {};
        const valid = man.posts.every((p) => p.candidates.some((c) => c.id === ch[p.id])) &&
          Object.keys(ch).length === man.posts.length;
        if (valid && commitBallot(eid, tok, ch, o.data.nonce) === b.data.commitment) {
          counted++;
          man.posts.forEach((p) => { counts[p.id][ch[p.id]]++; });
        } else badOpen++;
      });
      step('openings', 'Every opening matches its commitment', badOpen === 0,
        badOpen ? `${badOpen} openings missing or NOT matching their commitment` : `${counted} counted, ${spoiled} spoiled`);
      let resOk = false, resDetail = 'no signed result yet';
      if (res.length) {
        const r = res[res.length - 1].data;
        const sigOk = verifyMessage(boardKey, resultMessage(eid, r), big(r.sig));
        const same = canonical(r.counts) === canonical(counts) && r.counted === counted;
        resOk = sigOk && same;
        resDetail = resOk ? `your browser's recount of ${counted} ballots equals the signed result`
          : `signed result ${sigOk ? 'valid' : 'INVALID'}, recount ${same ? 'matches' : 'DIFFERS'}`;
      }
      step('recount', 'Independent recount matches the signed result', resOk, resDetail);
      tally = { counts, counted, spoiled };
    }
    return { verdict: steps.every((s) => s.ok) ? 'VERIFIED' : 'FAILED', steps, tally, firstBreak,
      ms: Math.round(performance.now() - t0), entries: entries.length };
  }

  const CV = { utf8, toHex, fromHex, concat, sha256, sha256hex, hmac, big, bigHex, modPow, modInv, gcd,
    randomBelow, fdh, pubKey, tokenMessage, newSecretHex, blind, unblind, verifyToken, verifyMessage,
    canonical, commitBallot, seal, entryHash, checkpointMessage, resultMessage, audit, bitLength };
  if (typeof module !== 'undefined' && module.exports) module.exports = CV;
  else root.CV = CV;
})(typeof window !== 'undefined' ? window : globalThis);
