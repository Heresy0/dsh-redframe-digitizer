import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

/** Parse this package's controlled name/JSON-quoted description frontmatter. */
export function loadWorkflowSkill(){
 const directory=path.join(path.dirname(fileURLToPath(import.meta.url)),'skills','redframe-digitize');
 const file=path.join(directory,'SKILL.md');
 const match=/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/.exec(fs.readFileSync(file,'utf8'));
 if(!match)throw Error('Packaged skill frontmatter is invalid');
 const name=/^name:\s*([a-z0-9]+(?:-[a-z0-9]+)*)\s*$/m.exec(match[1])?.[1];
 const encoded=/^description:\s*(".*")\s*$/m.exec(match[1])?.[1];
 const description=encoded?JSON.parse(encoded):undefined;
 if(!name||typeof description!=='string'||!description.trim()||!match[2].trim())throw Error('Packaged skill metadata/body is missing');
 return {name,description,content:match[2],source:'runtime',path:file,resourceBase:{kind:'directory',path:directory},invocation:{modelInvocable:true,userInvocable:true}};
}

export function registerWorkflowSkill(ctx){
 // Official optional-injection pattern: missing/late skills must not block MCP.
 if(typeof ctx.inject==='function')ctx.inject(['skills'],scoped=>{scoped.skills.register(loadWorkflowSkill());});
}
