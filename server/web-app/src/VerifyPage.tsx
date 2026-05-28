import { useState, useEffect } from 'react';
import { verifyMessage } from './verifier';
import type { VerificationResult } from './verifier';

export default function VerifyPage() {
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerificationResult | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const msg = params.get('message');
    if (msg) setMessage(msg);
  }, []);

  async function handleVerify() {
    setLoading(true);
    setResult(null);
    const outcome = await verifyMessage(message.trim());
    setResult(outcome);
    setLoading(false);
  }

  return (
    <main className="verify-page">

      <header className="verify-header">
        <h1>Message Integrity Verification</h1>
        <p>Paste a message below to verify it has not been tampered with. Verification queries the Sepolia blockchain directly — no server involved.</p>
      </header>

      <section className="verify-form">
        <textarea
          className="verify-input"
          rows={6}
          placeholder="Paste message content here..."
          value={message}
          onChange={e => setMessage(e.target.value)}
        />
        <button
          className="verify-button"
          onClick={handleVerify}
          disabled={!message.trim() || loading}
        >
          {loading ? 'Verifying...' : 'Verify'}
        </button>
      </section>

      {loading && (
        <p className="verify-loading">Querying Sepolia — this may take a few seconds...</p>
      )}

      {result && !loading && (
        <section className={`verify-result ${result.isValid ? 'result-pass' : 'result-fail'}`}>
          <h2>{result.isValid ? '✓ Verified' : '✗ Verification Failed'}</h2>
          <p className="verify-reason">{result.reason}</p>

          {result.timestamp && <div className="result-row"><span>Timestamp</span><span>{result.timestamp.toUTCString()}</span></div>}
          {result.batchIndex !== undefined && <div className="result-row"><span>Batch index</span><span>{result.batchIndex}</span></div>}
          {result.txHash && <div className="result-row"><span>Transaction</span><a href={`https://sepolia.etherscan.io/tx/${result.txHash}`} target="_blank" rel="noreferrer">{result.txHash.slice(0, 10)}...{result.txHash.slice(-8)}</a></div>}
          {result.merkleRoot && <div className="result-row"><span>Merkle root</span><span title={result.merkleRoot}>{result.merkleRoot.slice(0, 10)}...{result.merkleRoot.slice(-8)}</span></div>}
          {result.leafHash && <div className="result-row"><span>Leaf hash</span><span>{result.leafHash}</span></div>}
        </section>
      )}

    </main>
  );
}
