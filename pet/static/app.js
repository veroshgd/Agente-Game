'use strict';
const $ = id => document.getElementById(id);
let token='', state=null, busy=false, playing=false, showAll=false;
// away: the server's summary of real time that passed; shown only on arrival or return to the tab.
let away=null, returning=true;
let lang=localStorage.getItem('lang')||(navigator.language.startsWith('es')?'es':'zh');
// The engine and server speak Chinese; Spanish is translated here by source text.
const ES={
  '小小生活，慢慢长大':'Una pequeña vida, creciendo despacio','本地可玩原型 · 01':'Prototipo local jugable · 01',
  '一起，把日子过成回忆。':'Juntos, convirtamos los días en recuerdos.','给它一个机会，看看它会怎样选择。':'Dale una oportunidad y mira qué elige.',
  '正在登陆月球…':'Aterrizando en la luna…','取个名字 ↗':'Ponerle nombre ↗','月球小屋和月面花园':'Casita lunar y jardín lunar','月面花园':'Jardín lunar',
  '饱腹':'Saciedad','精力':'Energía','小屋':'Casa','此刻的小心思':'LO QUE PIENSA AHORA','过 1 小时':'Avanzar 1 hora','过 6 小时':'Avanzar 6 horas','过一天':'Avanzar un día',
  '即使关闭页面，现实每过 1 小时，它也过 1 个游戏小时（离开时最多补算 48 小时）。播放时每 3 秒再快进 1 小时。每次操作自动保存。':'Aunque cierres la página, por cada hora real pasa 1 hora de juego (al volver se recuperan como máximo 48 h). En reproducción, además, cada 3 segundos avanza 1 hora. Cada acción se guarda automáticamente.',
  '给生活一点小变化':'Pequeños cambios en su vida','你改变环境，它决定如何生活。':'Tú cambias el entorno; la criatura decide cómo vivir.',
  '✿ 开辟花园':'✿ Crear un jardín','让探索多一个去处':'Un nuevo lugar que explorar','▤ 放一本书':'▤ Dejar un libro','它可以选择读书':'Puede elegir leer',
  '♫ 放音乐盒':'♫ Poner una caja de música','为休息添一点舒适':'Hace el descanso más agradable','↗ 邀请米粒':'↗ Invitar a Mili','系统邻居 · 白天有空':'Vecina del sistema · libre de día',
  '慢慢有了自己的样子':'Poco a poco, encuentra su forma de ser','与出生时相比的变化。它们是行为倾向，不是固定的人格标签。':'Cambios respecto al nacimiento. Son tendencias de conducta, no etiquetas fijas de personalidad.',
  '这些变化从哪里来？':'¿De dónde vienen estos cambios?',
  '原有引擎按需求、目标、记忆和倾向选择行动；行动再更新倾向。新增的共同经历会给探索打分提供有限加成，影响随时间减弱。':'El motor elige acciones según necesidades, objetivos, recuerdos y tendencias; las acciones, a su vez, actualizan las tendencias. Las experiencias compartidas dan un bonus limitado a la puntuación de explorar, que se debilita con el tiempo.',
  '邻居 · 米粒':'Vecina · Mili','系统角色 · 08:00-20:00 有空':'Personaje del sistema · libre de 08:00 a 20:00','它的生活手记':'Su diario',
  '重要经历':'Momentos importantes','全部活动':'Toda la actividad','Life Engine · 从研究走向可玩的第一步':'Life Engine · primer paso de la investigación a algo jugable',
  '成长阶段与社交规则为原型设计，尚待用户验证。厨房自动补给，无需频繁投喂。':'Las etapas de crecimiento y las reglas sociales son de prototipo y aún no se han validado con usuarios. La cocina se reabastece sola; no hace falta alimentarla a menudo.',
  '导出存档':'Exportar partida','恢复存档':'Restaurar partida',
  '慢慢喜欢上的事':'Lo que ha llegado a gustarle',
  '只由真正做过、过得愉快的经历慢慢形成，不做就会慢慢淡去。它让这件事更有吸引力，但吃饭、休息和修小屋仍然优先。':'Se forma despacio solo con lo que de verdad hizo y disfrutó, y se va apagando si deja de hacerlo. Hace la actividad más atractiva, pero comer, descansar y arreglar la casa siguen yendo primero.',
  // Engine state (pet/engine.py)
  '幼年':'Pequeña','成长中':'Creciendo','成年':'Adulta','还没一起玩过':'Aún no han jugado juntas','开始熟悉':'Empiezan a conocerse','熟悉的伙伴':'Compañeras de confianza',
  '吃点东西':'Comer algo','休息':'Descansar','收集食物':'Recolectar comida','收集材料':'Recolectar materiales','整理小屋':'Arreglar la casita','四处探索':'Explorar los alrededores',
  '读书':'Leer','照料花园':'Cuidar el jardín','和米粒一起种花':'Plantar flores con Mili',
  '饿了，自己去厨房吃东西。':'Le entró hambre y fue a la cocina a comer algo.','累了，回家休息。':'Le entró sueño y volvió a casa a descansar.',
  '拿起家里的书读了一会儿。':'Tomó el libro de casa y leyó un rato.','用收集的材料改善了小屋。':'Mejoró la casita con los materiales que recogió.',
  '收集了一些整理小屋用的材料。':'Recogió materiales para arreglar la casita.','在附近找到了一些食物。':'Encontró algo de comida cerca.','独自探索了周围的环境。':'Exploró los alrededores por su cuenta.',
  '接受了这次邀请，和米粒种下一株花。':'Aceptó la invitación y plantó una flor con Mili.',
  '想起之前一起种花的经历，主动去找米粒，种下一株花。':'Recordó las flores que plantaron juntas, fue a buscar a Mili por iniciativa propia y plantaron otra.',
  '出门照料了花园。之前的共同经历增加了出门的吸引力。':'Salió a cuidar el jardín. Las experiencias compartidas le dieron más ganas de salir.',
  '出门照料了花园。今天还没有发生新的共同活动。':'Salió a cuidar el jardín. Hoy todavía no ha habido actividades compartidas.',
  '想去找米粒，可她今天不在家，就自己照料了花园。':'Quiso ir a ver a Mili, pero hoy no estaba en casa, así que cuidó el jardín sola.',
  '有一阵子没见米粒了，主动去找她，一起种下一株花。':'Hacía un tiempo que no veía a Mili; fue a buscarla por su cuenta y plantaron una flor juntas.',
  '想去找米粒，可她今天外出了，就自己照料了花园。':'Quiso ir a ver a Mili, pero hoy había salido, así que cuidó el jardín sola.',
  '想去找米粒，可她今天的接待次数已经满了，就自己照料了花园。':'Quiso ir a ver a Mili, pero hoy ya no recibía más visitas, así que cuidó el jardín sola.',
  '想去找米粒，可现在不是她的接待时间（08:00-20:00），就自己照料了花园。':'Quiso ir a ver a Mili, pero ahora no es su horario de visitas (08:00-20:00), así que cuidó el jardín sola.',
  '你好，小世界':'¡Hola, pequeño mundo!','小家伙诞生了。先取个名字，再一起认识这个家。':'Ha nacido una criaturita. Primero ponle un nombre; después, a conocer juntos este hogar.',
  '厨房补充了食物':'La cocina repuso comida','小屋会自动补充食物，饿了它会自己决定去吃。':'La casita repone la comida sola; cuando tenga hambre, decidirá por su cuenta ir a comer.',
  '小屋提供了应急照料':'La casita dio cuidados de emergencia','原型的安全照料降低了饥饿，避免生存惩罚。':'Los cuidados de seguridad del prototipo redujeron el hambre para evitar penalizaciones de supervivencia.',
  '记住了一件事':'Recordó algo','有了自己的名字':'Ya tiene nombre','家里有了新东西':'Algo nuevo en casa','给米粒留了一张邀请卡':'Le dejaste una invitación a Mili',
  '邀请持续一天；米粒在 08:00-20:00 有空。角色需要自己决定是否出门。':'La invitación dura un día; Mili está libre de 08:00 a 20:00. La criatura decide por sí misma si sale.',
  // Memories written by sim.py
  '世界里出现了一本书':'Apareció un libro en el mundo','开始有音乐了':'Empezó a sonar música','在远处发现了一片食物丰富的地方':'Descubrió a lo lejos un lugar con mucha comida',
  '读到了一些以前不知道的事':'Leyó cosas que no sabía','一场暴雨掀翻了屋顶':'Una tormenta arrancó el tejado','熬过了一段吃不饱的日子':'Sobrevivió a una temporada de hambre','有人给了我食物':'Alguien me dio comida',
  // Errors from pet/engine.py and pet/server.py
  '指令格式错误':'Formato de comando incorrecto','指令无效或本次原型的记录上限已到':'Comando no válido o se alcanzó el límite de registros del prototipo',
  '指令无效':'Comando no válido','时间步长无效':'Paso de tiempo no válido',
  '已达到本原型的操作上限。角色仍可查看，也可以导出存档。':'Se alcanzó el límite de acciones del prototipo. Puedes seguir viendo a la criatura y exportar la partida.',
  '剩余游戏时间不足以前进这么久（演示上限 10000 小时）。角色仍可查看，也可以导出存档。':'No queda tiempo de juego suficiente para avanzar tanto (límite de 10000 horas). Puedes seguir viendo a la criatura y exportar la partida.',
  '时间步长无效或已达到 10000 小时演示上限，请导出存档':'Paso de tiempo no válido o se alcanzó el límite de 10000 horas; exporta la partida',
  '名字请输入 1-20 个可见字符':'El nombre debe tener entre 1 y 20 caracteres visibles','未知物品':'Objeto desconocido','家里已经有这个了':'Eso ya está en casa',
  '先布置花园，再邀请邻居':'Primero crea el jardín y luego invita a la vecina','邀请还在等待回应':'La invitación aún espera respuesta','未知指令':'Comando desconocido',
  '不支持的存档版本':'Versión de partida no compatible','存档种子无效':'Semilla de partida no válida','存档指令数量无效':'Número de comandos de la partida no válido',
  '仅允许本机访问':'Solo se permite acceso local','请刷新页面后重试':'Recarga la página e inténtalo de nuevo','请求大小无效':'Tamaño de solicitud no válido',
  '存档写入失败，操作未提交。请检查目录权限或磁盘空间。':'No se pudo guardar; la acción no se aplicó. Revisa los permisos de la carpeta o el espacio en disco.',
  '存档过大':'La partida es demasiado grande','请求失败':'La solicitud falló'
};
const GOALS={improve_home:'hacer su casa más resistente',stock_food:'guardar más comida',see_the_world:'ir a ver lugares lejanos',learn:'leer un poco más',recover:'recuperar fuerzas'};
const GOAL_ZH={'把家弄得更结实':'improve_home','多存点吃的':'stock_food','去远处看看':'see_the_world','多读一点':'learn','把身体养回来':'recover'};
const OBJECTS={'一本书':'un libro','小音乐盒':'una cajita de música','花园入口':'la entrada al jardín'};
const PATTERNS=[
  [/^现在叫 (.*)。$/s,m=>`Ahora se llama ${m[1]}.`],
  [/^你准备了(.+)。是否使用，由它自己决定。$/,m=>`Preparaste ${OBJECTS[m[1]]||m[1]}. Decide por sí misma si lo usa.`],
  [/^和米粒一起种花（事件 #(\d+)）$/,m=>`Plantó flores con Mili (evento #${m[1]})`],
  [/^终于(.+)了$/,m=>GOAL_ZH[m[1]]?`Por fin consiguió ${GOALS[GOAL_ZH[m[1]]]}`:null],
  [/^想(.+)，但一直没做成$/,m=>GOAL_ZH[m[1]]?`Quería ${GOALS[GOAL_ZH[m[1]]]}, pero no lo consiguió`:null]
];
function tr(s){
  if(lang==='zh'||typeof s!=='string')return s;
  if(ES[s])return ES[s];
  for(const [re,fn] of PATTERNS){const m=s.match(re);if(m){const out=fn(m);if(out)return out;}}
  return s;
}
const hh=h=>String(h).padStart(2,'0')+':00';
const UI={
  zh:{clock:(d,h)=>`第 ${d} 天 · ${hh(h)}\n每个小变化，都有来处`,first:'刚来到这个世界',hint:'先给它取名，准备一些小物件，再让时间慢慢走。',
    goal:s=>`这段时间的目标：${s.goal.label}`,noGoal:'正在慢慢熟悉这个家。',traits:{caution:'谨慎',curiosity:'好奇',industry:'勤快'},sep:'、',
    shared:n=>`共同种花 ${n} 次`,memNote:(b,ids)=>`近期共同经历为探索提供最多 ${b} 分的加成，实际加成还取决于饱腹和精力。来源：${ids||'暂时没有近期经历'}。`,
    memEmpty:'还没有共同回忆。邀请卡本身不会增加亲密关系。',invitePending:'邀请已送达，正在等它决定。可以继续观察或让时间往前走。',
    inviteReady:'米粒白天有空。邀请只提供机会，不会强迫角色出门。',inviteFirst:'先开辟花园，再给米粒留一张邀请卡。',
    entryTime:(d,h,id)=>`第 ${d} 天 ${hh(h)} · #${id}`,change:'这次行动留下的变化：',
    parts:{core:'原有',garden:'花园',invitation:'邀请',memory:'共同记忆',boredom:'重复的无聊',eat_urgency:'饿了要吃',home_care:'小屋需要照料',gate:'饱腹/精力门控',raw:'门控前'},
    scoreLine:(items,net,final)=>`打分：${items} → 净变化 ${net}，最终 ${final}`,
    memoryUsed:ids=>`参与打分的共同经历：${ids}。`,memoryDecisive:a=>`没有这一项，这次会改为“${a}”。`,memoryNotDecisive:'它参与了打分，但没有改变这次选择。',
    rulesBadge:r=>`规则 v${r}`,
    rulesOld:(r,l)=>`这个角色按规则 v${r} 生活（最新为 v${l}）。为了不改写它已经发生的过去，旧角色会一直沿用创建时的规则。想体验新规则，请另开一个存档：双击 start_pet_v5.bat，或 python run_pet.py --save pet/data/v5-demo.json（原角色不受影响）。`,
    limitNote:why=>`已达到原型的${why==='commands'?'操作次数':'10000 游戏小时'}上限：时间不再前进。角色、手记和导出存档仍可正常使用。`,
    awaySkipped:(n,why)=>`有 ${n} 小时没有补算：已达到原型的${why==='commands'?'操作次数':'游戏时间'}上限。`,
    neighborRules:'米粒有自己的生活：有些日子会外出，每天最多主动接待两次。你的邀请卡她总会留出时间（仍在 08:00-20:00）。',
    prefNames:{read:'读书',garden:'独自照料花园',social:'米粒在家时，去找她而不是独处'},prefCount:n=>`${n} 次经历`,
    prefUsed:(name,n)=>`长期偏好“${name}”参与了打分（来自 ${n} 次经历的累积，不是某一件事）`,prefDecisive:a=>`即时检查：保持当前目标和其他状态不变，只去掉这一份偏好，这次会改为“${a}”。`,prefNotDecisive:'即时检查：只去掉这一份偏好（其他不变），仍会选择同一类行动，可能由另一份偏好接替。',
    prefScope:'这只检查行动大类，没有检查会去园艺还是拜访。',prefLife:'这不代表“如果它从没有过这段经历”。',
    empty:'这段时间还没有新的重要经历。切换“全部活动”看看日常吧。',history:(all,n)=>`显示最近 90 条中的${all?'全部活动':'重要经历'}；共 ${n} 条。导出存档可保留完整进度。`,
    play:'▶ 看它自己生活',pause:'Ⅱ 暂停观察',namePrompt:'给小家伙取个名字（1-20 个字符）',importConfirm:'恢复这个存档？当前进度会自动备份为 pet.before-import.json。',
    conn:'连接中断，请检查启动窗口是否还开着，再刷新页面。',title:'Life Engine · 小小生活',switchTo:'Español',html:'zh-CN',
    awayTitle:h=>h?`你不在的 ${h} 小时里`:'你不在的时候',awayText:list=>`它自己过着日子：${list}。`,awayNone:'这段时间它过得很平静。',awayChange:'这段时间的变化：'},
  es:{clock:(d,h)=>`Día ${d} · ${hh(h)}\nCada pequeño cambio tiene su origen`,first:'Acaba de llegar al mundo',hint:'Ponle un nombre, prepara algunos objetos y deja que el tiempo pase despacio.',
    goal:s=>`Objetivo de estos días: ${GOALS[s.goal.type]||s.goal.label}`,noGoal:'Poco a poco se va acostumbrando a su hogar.',traits:{caution:'Cautela',curiosity:'Curiosidad',industry:'Diligencia'},sep:', ',
    shared:n=>`Flores plantadas juntas: ${n}`,memNote:(b,ids)=>`Las experiencias compartidas recientes dan hasta ${b} puntos extra a explorar; el efecto real depende de la saciedad y la energía. Origen: ${ids||'ninguna experiencia reciente'}.`,
    memEmpty:'Aún no hay recuerdos compartidos. La invitación por sí sola no aumenta la amistad.',invitePending:'Invitación entregada; esperando a que decida. Puedes seguir observando o dejar pasar el tiempo.',
    inviteReady:'Mili está libre de día. La invitación solo da la oportunidad; no obliga a salir.',inviteFirst:'Primero crea el jardín y luego déjale una invitación a Mili.',
    entryTime:(d,h,id)=>`Día ${d} ${hh(h)} · #${id}`,change:'Cambios que dejó esta acción: ',
    parts:{core:'base',garden:'Jardín',invitation:'Invitación',memory:'Recuerdos compartidos',boredom:'Aburrimiento por repetir',eat_urgency:'Hambre',home_care:'La casa necesita cuidados',gate:'filtro de saciedad/energía',raw:'antes del filtro'},
    scoreLine:(items,net,final)=>`Puntuación: ${items} → cambio neto ${net}, total ${final}`,
    memoryUsed:ids=>`Recuerdos compartidos que contaron al decidir: ${ids}.`,memoryDecisive:a=>`Sin ellos, esta vez habría elegido “${a}”.`,memoryNotDecisive:'Contaron en la puntuación, pero no cambiaron la elección.',
    rulesBadge:r=>`Reglas v${r}`,
    rulesOld:(r,l)=>`Esta criatura vive con las reglas v${r} (las más recientes son v${l}). Para no reescribir su pasado, una criatura antigua conserva siempre las reglas con las que nació. Para probar las nuevas, abre otra partida: doble clic en start_pet_v5.bat, o python run_pet.py --save pet/data/v5-demo.json (la criatura original no cambia).`,
    limitNote:why=>`Se alcanzó el límite de ${why==='commands'?'acciones':'10000 horas de juego'} del prototipo: el tiempo ya no avanza. Puedes seguir viendo a la criatura, leer su diario y exportar la partida.`,
    awaySkipped:(n,why)=>`${n} ${n===1?'hora no se recuperó':'horas no se recuperaron'}: se alcanzó el límite de ${why==='commands'?'acciones':'tiempo de juego'} del prototipo.`,
    neighborRules:'Mili tiene su propia vida: algunos días sale y recibe como mucho dos visitas espontáneas al día. Para tu invitación siempre hace un hueco (dentro de 08:00-20:00).',
    prefNames:{read:'Leer',garden:'Cuidar el jardín a solas',social:'Si Mili está libre, ir a verla en vez de estar sola'},prefCount:n=>`${n} ${n===1?'experiencia':'experiencias'}`,
    prefUsed:(name,n)=>`El gusto por «${name}» contó en la puntuación (formado a lo largo de ${n} experiencias, no por un solo hecho)`,prefDecisive:a=>`Comprobación inmediata: quitando solo este gusto, con el objetivo actual y todo lo demás igual, esta vez habría elegido «${a}».`,prefNotDecisive:'Comprobación inmediata: quitando solo este gusto (lo demás igual), habría elegido el mismo tipo de acción; otro gusto puede tomar el relevo.',
    prefScope:'Solo se comprueba el tipo de acción, no si iría al jardín o a ver a Mili.',prefLife:'No equivale a «si nunca hubiera vivido esas experiencias».',
    empty:'Aún no hay momentos importantes en este periodo. Cambia a “Toda la actividad” para ver el día a día.',history:(all,n)=>`Mostrando ${all?'toda la actividad':'los momentos importantes'} de los últimos 90 registros; ${n} en total. Exporta la partida para conservar todo el progreso.`,
    play:'▶ Verla vivir',pause:'Ⅱ Pausar',namePrompt:'Ponle un nombre a la criaturita (1-20 caracteres)',importConfirm:'¿Restaurar esta partida? El progreso actual se guardará como copia en pet.before-import.json.',
    conn:'Se perdió la conexión. Comprueba que la ventana del servidor sigue abierta y recarga la página.',title:'Life Engine · Una pequeña vida',switchTo:'中文',html:'es',
    awayTitle:h=>h?`Mientras no estabas (${h} ${h===1?'hora':'horas'})`:'Mientras no estabas',awayText:list=>`Siguió con su vida: ${list}.`,awayNone:'Fue un rato tranquilo.',awayChange:'Cambios en este tiempo: '}
};
const t=()=>UI[lang];
const text=(id,value)=>{$(id).textContent=value;};
function error(message){text('error',message);$('error').hidden=!message;}
function stop(){playing=false;text('play',t().play);}
function applyLang(){
  document.documentElement.lang=t().html;document.title=t().title;text('lang',t().switchTo);
  for(const el of document.querySelectorAll('[data-i18n]')){el.dataset.zh??=el.textContent;el.textContent=tr(el.dataset.zh);}
  const scene=$('scene');scene.dataset.zh??=scene.getAttribute('aria-label');scene.setAttribute('aria-label',tr(scene.dataset.zh));
  text('play',playing?t().pause:t().play);
  if(state)render(state);
  renderAway();
}
function renderAway(){
  $('away').hidden=!away;
  if(!away)return;
  text('away-title',t().awayTitle(away.hours));
  const counts=Object.entries(away.counts).sort((a,b)=>b[1]-a[1]).map(([title,n])=>`${tr(title)} ×${n}`);
  // Nothing ran (the prototype limit stopped time): say only that, not "a quiet while".
  text('away-text',counts.length?t().awayText(counts.join(t().sep)):(away.hours?t().awayNone:''));
  const labels=t().traits;const changes=Object.entries(away.traits).filter(([,n])=>Math.abs(n)>=.1).map(([k,n])=>`${labels[k]} ${n>=0?'+':''}${n.toFixed(1)}`);
  text('away-traits',(changes.length?t().awayChange+changes.join(' · '):'')+(away.skipped_hours?(changes.length?' ':'')+t().awaySkipped(away.skipped_hours,away.limit):''));
  const list=$('away-list');list.replaceChildren();
  for(const e of away.highlights){
    const div=document.createElement('div');div.className='entry';
    const title=document.createElement('strong');title.textContent=`#${e.id} · ${tr(e.title)}`;
    const body=document.createElement('p');body.textContent=tr(e.text);div.append(title,body);list.append(div);
  }
}
const ids=list=>list.map(id=>'#'+id).join(t().sep);
// Signed numbers with a real minus sign: never "+-0.6".
const signed=x=>(x<0?'−':'+')+Math.abs(x).toFixed(1);
const ACTION_ZH={eat:'吃点东西',sleep:'休息',gather_food:'收集食物',gather_material:'收集材料',build:'整理小屋',explore:'四处探索',read:'读书'};
function decisionNotes(e){
  const d=e.decision;if(!d)return [];
  const p=t().parts,items=[];
  for(const key of ['garden','invitation','memory'])if(d[key])items.push(`${p[key]} ${signed(d[key])}`);
  if(d.garden||d.invitation||d.memory_raw)items.push(`${p.gate} ×${d.gate.toFixed(2)}`+(d.memory_raw&&d.gate<1?` (${p.memory} ${p.raw} ${signed(d.memory_raw)})`:''));
  if(d.eat_urgency)items.push(`${p.eat_urgency} ${signed(d.eat_urgency)}`);
  if(d.home_care)items.push(`${p.home_care} ${signed(d.home_care)}`);
  if(d.boredom)items.push(`${p.boredom} ${signed(-d.boredom)}`);
  if(d.preference)items.push(`${t().prefNames[d.pref_key]} ${signed(d.preference)}`);
  if(!items.length)return [];
  const notes=[t().scoreLine([`${p.core} ${d.core.toFixed(1)}`,...items].join(' · '),signed(d.net),d.final.toFixed(1))];
  if(e.cause_ids&&e.cause_ids.length&&d.memory){
    notes.push(t().memoryUsed(ids(e.cause_ids))+' '+(d.memory_decisive?t().memoryDecisive(tr(ACTION_ZH[d.runner_up_action]||d.runner_up_action)):t().memoryNotDecisive));
  }
  if(d.preference){
    const cf=d.pref_counterfactual,end=lang==='zh'?'。':'. ';
    let note=t().prefUsed(t().prefNames[d.pref_key],d.pref_experiences)+end;
    if(cf)note+=(d.pref_decisive?t().prefDecisive(tr(ACTION_ZH[cf.choice_without]||cf.choice_without)):t().prefNotDecisive)+(e.core_action==='explore'?' '+t().prefScope:'')+' '+t().prefLife;
    notes.push(note);
  }
  return notes;
}
function render(s){
  state=s;text('pet-name',s.name);text('stage',tr(s.stage));text('clock',t().clock(s.day,s.hour));
  for(const key of ['satiety','energy','home']){if(s[key]===undefined)continue;$(key).value=s[key];text(key+'-value',s[key]);}
  $('house').classList.toggle('worn',s.home<20);
  $('rules-badge').hidden=s.rules===undefined;if(s.rules!==undefined)text('rules-badge',t().rulesBadge(s.rules));
  const old=s.rules!==undefined&&s.rules<s.latest_rules;$('rules-note').hidden=!old;if(old)text('rules-note',t().rulesOld(s.rules,s.latest_rules));
  const lim=s.limits||{};const blocked=lim.can_advance===false;$('limit-note').hidden=!blocked;
  if(blocked){stop();text('limit-note',t().limitNote(lim.commands_left===0?'commands':'ticks'));}
  text('activity',s.last?tr(s.last.title):t().first);text('thought',s.last?tr(s.last.text):t().hint);
  text('goal',s.goal?t().goal(s):t().noGoal);
  $('creature').className='creature '+(s.last?s.last.action:'');
  $('neighbor').hidden=!(s.last&&s.last.action==='visit');
  for(const key of ['book','music'])$(key).hidden=!s.objects.includes(key);
  text('flowers',s.flowers?'✿'.repeat(Math.min(8,s.flowers)):(s.objects.includes('garden')?'·  ·  ·':''));
  const traits=$('traits');traits.replaceChildren();
  for(const [key,value] of Object.entries(s.traits)){
    const row=document.createElement('div');row.className='trait';
    const label=document.createElement('div');label.className='trait-label';
    const title=document.createElement('span');title.textContent=t().traits[key];
    const number=document.createElement('span');const delta=(value-s.birth_traits[key]).toFixed(1);number.textContent=`${value} · ${delta>=0?'+':''}${delta}`;
    label.append(title,number);const track=document.createElement('div');track.className='track';const bar=document.createElement('span');bar.style.width=value+'%';track.append(bar);row.append(label,track);traits.append(row);
  }
  $('prefs-box').hidden=!s.preferences;
  if(s.preferences){const box=$('prefs');box.replaceChildren();
    for(const [key,p] of Object.entries(s.preferences)){
      const row=document.createElement('div');row.className='trait';
      const label=document.createElement('div');label.className='trait-label';
      const name=document.createElement('span');name.textContent=t().prefNames[key];
      const n=document.createElement('span');n.textContent=t().prefCount(p.experiences);
      label.append(name,n);const track=document.createElement('div');track.className='track';
      const bar=document.createElement('span');bar.style.width=Math.round(Math.min(1,p.value)*100)+'%';track.append(bar);row.append(label,track);box.append(row);}}
  text('relationship',tr(s.relationship));text('shared',t().shared(s.shared_count));
  $('neighbor-rules').hidden=!(s.rules>=3);text('neighbor-rules',t().neighborRules);
  text('memory-note',s.shared_count?t().memNote(s.memory_bonus,ids(s.memory_ids)):t().memEmpty);
  for(const button of document.querySelectorAll('[data-object]'))button.disabled=s.objects.includes(button.dataset.object)||busy||lim.can_act===false;
  $('invite').disabled=!s.objects.includes('garden')||s.invitation_pending||busy||lim.can_act===false;
  for(const button of document.querySelectorAll('[data-hours]'))button.disabled=busy||blocked||Number(button.dataset.hours)>lim.ticks_left;
  $('play').disabled=busy||blocked;$('rename').disabled=busy||lim.can_act===false;
  text('invite-status',s.invitation_pending?t().invitePending:(s.objects.includes('garden')?t().inviteReady:t().inviteFirst));
  renderTimeline();
}
function renderTimeline(){
  if(!state)return;
  $('filter-all').setAttribute('aria-pressed',String(showAll));$('filter-story').setAttribute('aria-pressed',String(!showAll));
  const list=$('timeline');list.replaceChildren();
  const events=state.events.filter(e=>showAll||e.kind!=='action'||e.action==='visit');
  for(const e of [...events].reverse()){
    const div=document.createElement('div');div.className='entry';
    const time=document.createElement('time');time.textContent=t().entryTime(Math.floor(e.tick/24)+1,e.tick%24,e.id);
    const title=document.createElement('strong');title.textContent=tr(e.title);
    const body=document.createElement('p');body.textContent=tr(e.text);div.append(time,title,body);
    for(const note of decisionNotes(e)){const small=document.createElement('small');small.className='decision';small.textContent=note;div.append(small);}
    if(e.before&&e.after){const labels=t().traits;const changes=Object.keys(labels).map(k=>[labels[k],e.after[k]-e.before[k]]).filter(pair=>Math.abs(pair[1])>=.05);if(changes.length){const change=document.createElement('p');change.textContent=t().change+changes.map(([label,n])=>`${label} ${n>=0?'+':''}${n.toFixed(1)}`).join(' · ');div.append(change);}}
    list.append(div);
  }
  if(!events.length)list.textContent=t().empty;
  text('history-note',t().history(showAll,state.total_events));
}
async function request(path,body){
  if(busy)return;busy=true;error('');
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{
    const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Pet-Token':token},body:JSON.stringify(body)});
    const result=await response.json();
    if(!response.ok){if(result.state){state=result.state;token=result.token||token;}throw new Error(result.error||'请求失败');}
    token=result.token;state=result.state;
    if(result.away&&returning){away=result.away;renderAway();}
    returning=false;
  }catch(e){stop();error(e.message==='Failed to fetch'?t().conn:tr(e.message));}
  finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=!state);$('lang').disabled=false;if(state)render(state);}
}
const command=(kind,value)=>request('/api/command',{kind,value});
document.querySelectorAll('[data-hours]').forEach(b=>b.addEventListener('click',()=>command('advance',Number(b.dataset.hours))));
document.querySelectorAll('[data-object]').forEach(b=>b.addEventListener('click',()=>command('object',b.dataset.object)));
$('invite').addEventListener('click',()=>command('invite',null));
$('rename').addEventListener('click',()=>{stop();const value=prompt(t().namePrompt,state.name);if(value!==null)command('name',value);});
$('play').addEventListener('click',()=>{playing=!playing;text('play',playing?t().pause:t().play);});
$('lang').addEventListener('click',()=>{lang=lang==='zh'?'es':'zh';localStorage.setItem('lang',lang);applyLang();});
$('filter-story').addEventListener('click',()=>{showAll=false;renderTimeline();});
$('filter-all').addEventListener('click',()=>{showAll=true;renderTimeline();});
$('import-button').addEventListener('click',()=>{stop();$('import-file').click();});
$('import-file').addEventListener('change',async()=>{const file=$('import-file').files[0];if(!file)return;try{if(file.size>2000000)throw new Error('存档过大');const data=JSON.parse(await file.text());if(confirm(t().importConfirm))await request('/api/import',data);}catch(e){error(tr(e.message));}finally{$('import-file').value='';}});
$('away-close').addEventListener('click',()=>{away=null;renderAway();});
document.addEventListener('visibilitychange',()=>{if(document.hidden){stop();returning=true;}else request('/api/state');});
setInterval(()=>{if(playing&&!busy&&!document.hidden&&state&&state.limits.can_advance)command('advance',1);},3000);
// Real time also passes with the page open: ask the server to catch up every minute.
setInterval(()=>{if(!playing&&!busy&&!document.hidden)request('/api/state');},60000);
applyLang();
request('/api/state');
