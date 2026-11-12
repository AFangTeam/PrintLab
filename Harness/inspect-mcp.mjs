// PrintLab-owned stdio client. Calls only the public offline inspection tool.
import fs from 'node:fs';
import {spawn} from 'node:child_process';
import path from 'node:path';

const [entry, artifact, plate, model] = process.argv.slice(2);
let server;
try {
  const pkg = JSON.parse(fs.readFileSync(path.resolve(entry, '../../package.json'), 'utf8'));
  if (pkg.name !== 'bambu-printer-mcp' || pkg.version !== '1.1.33') throw Error('Install the verified bambu-printer-mcp@1.1.33 inspector.');
  server = spawn(process.execPath, [entry], {stdio: ['pipe', 'pipe', 'pipe'], env: {...process.env, MCP_TRANSPORT: 'stdio'}});
  const pending = new Map();
  let buffer = '', bytes = 0, id = 0;
  const fail = error => { for (const p of pending.values()) p.reject(error); pending.clear(); };
  server.on('error', fail);
  server.on('exit', () => fail(Error('Inspector exited before returning evidence.')));
  server.stderr.on('data', () => {}); // No credentials or unbounded diagnostic buffers.
  const send = message => server.stdin.write(JSON.stringify({jsonrpc:'2.0', ...message}) + '\n');
  server.stdin.on('error', fail);
  server.stdout.setEncoding('utf8');
  server.stdout.on('data', chunk => {
    bytes += chunk.length;
    if (bytes > 4 * 1024 * 1024) { fail(Error('Oversized MCP response.')); server.kill(); return; }
    buffer += chunk.toString('utf8');
    let end;
    while ((end = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, end); buffer = buffer.slice(end + 1);
      try {
        const message = JSON.parse(line);
        if (message.method && message.id !== undefined) {
          send({id:message.id, error:{code:-32601,message:'Client does not provide tools or user authorization.'}});
        } else if (pending.has(message.id)) {
          const waiter = pending.get(message.id); pending.delete(message.id);
          message.error ? waiter.reject(Error(message.error.message)) : waiter.resolve(message.result);
        }
      } catch { fail(Error('Invalid MCP response.')); }
    }
  });
  const request = (method, params) => new Promise((resolve, reject) => {
    const requestId = ++id; pending.set(requestId, {resolve,reject}); send({id:requestId,method,params});
  });
  await request('initialize', {protocolVersion:'2024-11-05', capabilities:{}, clientInfo:{name:'printlab-offline-inspector',version:'1.0.0'}});
  send({method:'notifications/initialized'});
  const result = await request('tools/call', {name:'inspect_print_file',arguments:{file_path:artifact,bambu_model:model,plate_index:Number(plate)}});
  if (result.isError) throw Error(result.content?.find(c=>c.type==='text')?.text || 'Inspector rejected the file.');
  const receipt = result.structuredContent ?? JSON.parse(result.content.find(c=>c.type==='text').text);
  process.stdout.write(JSON.stringify(receipt));
} catch (error) {
  process.stdout.write(JSON.stringify({error:String(error.message)}));
  process.exitCode = 1;
} finally {
  if (server) server.kill();
}
