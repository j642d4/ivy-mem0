// Reads a flat-JSON secret string from stdin, writes shell `export KEY='VALUE'`
// lines to stdout so entrypoint.sh can eval them into the process environment.
const chunks = [];
process.stdin.on('data', chunk => chunks.push(chunk));
process.stdin.on('end', () => {
  const secret = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  for (const [key, value] of Object.entries(secret)) {
    const escaped = String(value).replace(/'/g, "'\\''");
    process.stdout.write(`export ${key}='${escaped}'\n`);
  }
});
