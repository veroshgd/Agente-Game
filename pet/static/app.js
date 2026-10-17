'use strict';
const $ = id => document.getElementById(id);
let token='', state=null, busy=false, playing=false, showAll=false;
const text=(id,value)=>{$(id).textContent=value;};
function error(message){text('error',message);$('error').hidden=!message;}
function stop(){playing=false;text('play','▶ 看它自己生活');}
function render(s){
  state=s;text('pet-name',s.name);text('stage',s.stage);text('clock',`第 ${s.day} 天 · ${String(s.hour).padStart(2,'0')}:00\n每个小变化，都有来处`);
  for(const key of ['satiety','energy']){$(key).value=s[key];text(key+'-value',s[key]);}
  text('activity',s.last?s.last.title:'刚来到这个世界');text('thought',s.last?s.last.text:'先给它取名，准备一些小物件，再让时间慢慢走。');
  text('goal',s.goal?`这段时间的目标：${s.goal.label}`:'正在慢慢熟悉这个家。');
  $('creature').className='creature '+(s.last?s.last.action:'');
  $('neighbor').hidden=!(s.last&&s.last.action==='visit');
  for(const key of ['book','music'])$(key).hidden=!s.objects.includes(key);
  text('flowers',s.flowers?'✿'.repeat(Math.min(8,s.flowers)):(s.objects.includes('garden')?'·  ·  ·':''));
  const traits=$('traits');traits.replaceChildren();
  const labels={caution:'谨慎',curiosity:'好奇',industry:'勤快'};
  for(const [key,value] of Object.entries(s.traits)){
    const row=document.createElement('div');row.className='trait';
    const label=document.createElement('div');label.className='trait-label';
    const title=document.createElement('span');title.textContent=labels[key];
    const number=document.createElement('span');const delta=(value-s.birth_traits[key]).toFixed(1);number.textContent=`${value} · ${delta>=0?'+':''}${delta}`;
    label.append(title,number);const track=document.createElement('div');track.className='track';const bar=document.createElement('span');bar.style.width=value+'%';track.append(bar);row.append(label,track);traits.append(row);
  }
  text('relationship',s.relationship);text('shared',`共同种花 ${s.shared_count} 次`);
  text('memory-note',s.shared_count?`近期共同经历为探索提供最多 ${s.memory_bonus} 分的加成，实际加成还取决于饱腹和精力。来源：${s.memory_ids.map(id=>'#'+id).join('、')||'暂时没有近期经历'}。`:'还没有共同回忆。邀请卡本身不会增加亲密关系。');
  for(const button of document.querySelectorAll('[data-object]'))button.disabled=s.objects.includes(button.dataset.object)||busy;
  $('invite').disabled=!s.objects.includes('garden')||s.invitation_pending||busy;
  text('invite-status',s.invitation_pending?'邀请已送达，正在等它决定。可以继续观察或让时间往前走。':(s.objects.includes('garden')?'米粒白天有空。邀请只提供机会，不会强迫角色出门。':'先开辟花园，再给米粒留一张邀请卡。'));
  renderTimeline();
}
function renderTimeline(){
  if(!state)return;
  $('filter-all').setAttribute('aria-pressed',String(showAll));$('filter-story').setAttribute('aria-pressed',String(!showAll));
  const list=$('timeline');list.replaceChildren();
  const events=state.events.filter(e=>showAll||e.kind!=='action'||e.action==='visit');
  for(const e of [...events].reverse()){
    const div=document.createElement('div');div.className='entry';
    const time=document.createElement('time');time.textContent=`第 ${Math.floor(e.tick/24)+1} 天 ${String(e.tick%24).padStart(2,'0')}:00 · #${e.id}`;
    const title=document.createElement('strong');title.textContent=e.title;
    const body=document.createElement('p');body.textContent=e.text;div.append(time,title,body);
    if(e.cause_ids&&e.cause_ids.length){const cause=document.createElement('small');cause.textContent=`决策前参考：${e.cause_ids.map(id=>'#'+id).join('、')} · 探索得分增加 ${e.score_bonus}`;div.append(cause);}
    if(e.before&&e.after){const labels={caution:'谨慎',curiosity:'好奇',industry:'勤快'};const changes=Object.keys(labels).map(k=>[labels[k],e.after[k]-e.before[k]]).filter(pair=>Math.abs(pair[1])>=.05);if(changes.length){const change=document.createElement('p');change.textContent='这次行动留下的变化：'+changes.map(([label,n])=>`${label} ${n>=0?'+':''}${n.toFixed(1)}`).join(' · ');div.append(change);}}
    list.append(div);
  }
  if(!events.length)list.textContent='这段时间还没有新的重要经历。切换“全部活动”看看日常吧。';
  text('history-note',`显示最近 90 条中的${showAll?'全部活动':'重要经历'}；共 ${state.total_events} 条。导出存档可保留完整进度。`);
}
async function request(path,body){
  if(busy)return;busy=true;error('');
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{
    const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Pet-Token':token},body:JSON.stringify(body)});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'请求失败');
    token=result.token;state=result.state;
  }catch(e){stop();error(e.message==='Failed to fetch'?'连接中断，请检查启动窗口是否还开着，再刷新页面。':e.message);}
  finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=!state);if(state)render(state);}
}
const command=(kind,value)=>request('/api/command',{kind,value});
document.querySelectorAll('[data-hours]').forEach(b=>b.addEventListener('click',()=>command('advance',Number(b.dataset.hours))));
document.querySelectorAll('[data-object]').forEach(b=>b.addEventListener('click',()=>command('object',b.dataset.object)));
$('invite').addEventListener('click',()=>command('invite',null));
$('rename').addEventListener('click',()=>{stop();const value=prompt('给小家伙取个名字（1-20 个字符）',state.name);if(value!==null)command('name',value);});
$('play').addEventListener('click',()=>{playing=!playing;text('play',playing?'Ⅱ 暂停观察':'▶ 看它自己生活');});
$('filter-story').addEventListener('click',()=>{showAll=false;renderTimeline();});
$('filter-all').addEventListener('click',()=>{showAll=true;renderTimeline();});
$('import-button').addEventListener('click',()=>{stop();$('import-file').click();});
$('import-file').addEventListener('change',async()=>{const file=$('import-file').files[0];if(!file)return;try{if(file.size>2000000)throw new Error('存档过大');const data=JSON.parse(await file.text());if(confirm('恢复这个存档？当前进度会自动备份为 pet.before-import.json。'))await request('/api/import',data);}catch(e){error(e.message);}finally{$('import-file').value='';}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
setInterval(()=>{if(playing&&!busy&&!document.hidden)command('advance',1);},3000);
request('/api/state');
