// Test the actual inline script without opening a browser or using UI automation.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('Zero Hour Options.html', 'utf8');
const elements = {};
for (const match of html.matchAll(/\bid="([^"]+)"/g)) {
  elements[match[1]] = {value:'',checked:false,textContent:'',disabled:false, listeners:{},
    addEventListener(event,fn){this.listeners[event]=fn;}};
}
for(const match of html.matchAll(/<input\b[^>]*>/g)){
 const id=match[0].match(/id="([^"]+)"/)[1],value=match[0].match(/value="([^"]*)"/);
 if(value)elements[id].value=value[1];
 elements[id].checked=/\bchecked\b/.test(match[0]);
}
elements['sell-refund'].value = 'normal_refund';
elements['victory-goal'].value='all_sets';elements['goal-final'].value='usa';
elements.deathmode.value = 'full_restart';
for(const name of ['usa','china','gla'])elements[name].checked = true;
elements.challenge.value = '0';
elements.startcount.value = '1';
const context = {document:{getElementById:id=>elements[id],querySelectorAll:()=>
    [...html.matchAll(/<(?:input|select)\b[^>]*\bid="([^"]+)"/g)].map(m=>elements[m[1]])}};
vm.createContext(context);
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
assert.match(elements.yaml.textContent,/name: "ZeroHour"/);
assert.match(elements.yaml.textContent,/trap_percentage: 50/);
assert.match(elements.yaml.textContent,/mission_report_weight: 0/);
assert.match(elements.yaml.textContent,/supply_drop_weight: 50/);
assert.match(elements.yaml.textContent,/reinforcements_weight: 50/);
assert.match(elements['trap-summary'].textContent,/0 traps and 12 non-trap filler slots/);
elements['trap-enabled'].checked=true;context.update();
assert.match(elements['trap-summary'].textContent,/6 traps and 6 non-trap filler slots/);
assert.match(elements['filler-summary'].textContent,/Mission Report 0.0, Supply Drop 1.5, Reinforcements 1.5, Production Surge 1.5, Construction Boost 1.5/);
elements['trap-enabled'].checked=false;
// Keep exercising the legacy report-only configuration as well as new defaults.
elements['report-filler'].value='50';elements['production-filler'].value=elements['construction-filler'].value=elements['supply-filler'].value=elements['reinforcement-filler'].value='0';context.update();
assert.match(elements.yaml.textContent,/usa_campaign: true/);
assert.match(elements.yaml.textContent,/mission_completion_checks: 1/);
assert.match(elements.yaml.textContent,/set_completion_checks: 5/);
for(const key of ['power_outage_weight','cash_theft_weight','production_shutdown_weight','sell_random_building_weight'])assert.match(elements.yaml.textContent,new RegExp(key+': 50'));
assert.equal(elements.summary.textContent,'30 total checks (including set bonuses)');
assert.equal(elements['check-total'].textContent,'30');
assert.equal(elements['story-check-total'].textContent,'15');
assert.equal(elements['challenge-check-total'].textContent,'0');
assert.equal(elements['set-check-total'].textContent,'15');
assert.match(elements.yaml.textContent,/death_link: false/);
for(const key of ['general_builder_unlocks','reveal_minimap','carpet_bomb','patriot_airdrop','emergency_repair'])assert.match(elements.yaml.textContent,new RegExp(key+': true'));
assert.equal(elements.download.disabled,false);
assert.match(elements['trap-summary'].textContent,/12 Mission Reports/);
assert.match(html,/<h2>Permanent Unlocks<\/h2>/);
assert.match(html,/<h2[^>]*>Deathlink<\/h2>/);
assert.match(html,/<title>Zero Hour - YAML Creator<\/title>/);
assert.match(html,/Three CIA Agents and a Heroic \(level 3\) Humvee carrying five Heroic Missile Defenders/);
assert.doesNotMatch(html,/[^\x00-\x7f]/);
// Exercise the existing capacity matrix with the three standard builders only.
// The enabled-by-default complete pool is checked above and in the builder cases below.
for(const id of ['general-builders','reveal-minimap','carpet-bomb','patriot-airdrop','emergency-repair'])elements[id].checked=false;
elements['general-builders'].listeners.input();
elements.deathlink.checked=true;elements.deathlink.listeners.input();
assert.match(elements.yaml.textContent,/death_link: true/);
elements.deathlink.checked=false;elements.deathlink.listeners.input();
elements.deathmode.value='quick_reset';elements.deathmode.listeners.input();
assert.match(elements.yaml.textContent,/death_link_mode: quick_reset/);
assert.match(elements.deathnote.textContent,/Watch the opening once/);
elements.deathmode.value='full_restart';elements.deathmode.listeners.input();
assert.match(elements.yaml.textContent,/death_link_mode: full_restart/);
assert.match(elements.deathnote.textContent,/replays the opening intro/);
const yamlExports=[];
for(let mask=0;mask<16;mask++)for(let count=0;count<=9;count++){
  ['usa','china','gla','exclude'].forEach((id,index)=>elements[id].checked=Boolean(mask&(1<<index)));
  elements.challenge.value=String(count);
  elements.challenge.listeners.input();
  assert.equal(elements.download.disabled,(mask&7)===0 && count===0);
  assert.match(elements.yaml.textContent,new RegExp('generals_challenge_campaigns: '+count+'\\n'));
  if(!elements.download.disabled)yamlExports.push(elements.yaml.textContent);
}
assert.equal(elements.summary.textContent,'138 total checks (including set bonuses)');
for(let cash=0;cash<=10;cash++)for(let percent=0;percent<=100;percent+=10){
 elements.cash.value=String(cash);elements['trap-percent'].value=String(percent);elements.cash.listeners.input();
 assert.equal(elements.download.disabled,false);
 assert.match(elements.yaml.textContent,new RegExp('progressive_starting_cash: '+cash+'\\n'));
 assert.match(elements.yaml.textContent,new RegExp('trap_percentage: '+percent+'\\n'));
}
assert.doesNotMatch(elements.yaml.textContent, /power_outage_traps:|cash_thefts:|production_shutdowns:/);
assert.equal(elements['trap-settings'].hidden,true);
assert.equal(elements['trap-percent'].disabled,true);
elements['trap-enabled'].checked=true;elements['trap-enabled'].listeners.input();
assert.equal(elements['trap-settings'].hidden,false);
assert.equal(elements['trap-percent'].disabled,false);
elements['sell-weight'].value='0';elements['power-weight'].value='3';elements['theft-weight'].value='1';elements['shutdown-weight'].value='0';elements['power-weight'].listeners.input();
assert.match(elements['power-share'].textContent,/75.0%/);
assert.match(elements['theft-share'].textContent,/25.0%/);
assert.equal(elements['shutdown-share'].textContent,'Excluded.');
assert.match(elements.yaml.textContent,/power_outage_weight: 3/);
assert.match(elements.yaml.textContent,/production_shutdown_weight: 0/);
elements['power-weight'].value=elements['theft-weight'].value='0';elements['power-weight'].listeners.input();
assert.equal(elements.download.disabled,true);
elements['trap-percent'].value='0';elements['trap-percent'].listeners.input();assert.equal(elements.download.disabled,false);
elements['trap-percent'].value='100';elements['trap-enabled'].checked=false;elements['trap-enabled'].listeners.input();assert.equal(elements.download.disabled,false);
assert.equal(elements['power-weight'].value,'0'); // preferences preserved while disabled
for(const id of ['power-weight','theft-weight','shutdown-weight','sell-weight'])elements[id].value='1';

elements.challenge.value='0';elements.china.checked=elements.gla.checked=false;
elements.cash.value='7';elements.cash.listeners.input();
assert.equal(elements.download.disabled,true);
elements.cash.value='6';elements.cash.listeners.input();assert.equal(elements.download.disabled,false);

elements.start0.checked=true;elements.start0.listeners.input();
assert.match(elements.yaml.textContent,/starting_mission_sets: \["USA"\]/);
elements.start2.checked=true;elements.start2.listeners.input();assert.equal(elements.download.disabled,true);
elements.china.checked=true;elements.startcount.value='2';elements.startcount.listeners.input();
assert.equal(elements.download.disabled,false);
assert.match(elements.yaml.textContent,/starting_set_count: 2/);
elements.start3.checked=true;elements.startcount.value='3';elements.startcount.listeners.input();
assert.equal(elements.download.disabled,true); // chosen general needs a challenge slot
elements.challenge.value='1';elements.challenge.listeners.input();assert.equal(elements.download.disabled,false);

// Restore the default three campaigns and check exact replacement counts.
for(const id of ['usa','china','gla'])elements[id].checked=true;
for(let i=0;i<12;i++)elements['start'+i].checked=false;
elements.exclude.checked=false;elements.challenge.value='0';elements.startcount.value='1';elements.cash.value='0';
elements['trap-enabled'].checked=true;
for(const [percent,traps,reports] of [[0,0,25],[25,6,19],[50,12,13],[100,25,0]]){
 elements['trap-percent'].value=String(percent);elements['trap-percent'].listeners.input();
 assert.equal(elements['trap-summary'].textContent,`Pool preview: ${traps} traps and ${reports} Mission Reports.`);
 assert.equal(elements.download.disabled,false);
}
elements.player.value='quoted "name';elements.player.listeners.input();
assert.match(elements.yaml.textContent,/name: "quoted \\"name"/);
elements.player.value='  ';elements.player.listeners.input();
assert.equal(elements.download.disabled,true);
if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify(yamlExports));
console.log('PASS: 160 campaign configurations, 121 cash/percentage combinations, trap toggle, weights and filler previews, capacity limits, names, and YAML preview updates.');

// Twelve-builder capacity and YAML switch use the actual creator script.
elements.player.value="Nin-ZeroHour";
for(const name of ['usa','china','gla'])elements[name].checked=true;
elements.challenge.value='0';elements.startcount.value='1';
for(let i=0;i<12;i++)elements['start'+i].checked=false;
elements.cash.value='0';
elements['trap-enabled'].checked=false;
elements['general-builders'].checked=true;elements['general-builders'].listeners.input();
assert.match(elements.yaml.textContent,/general_builder_unlocks: true/);
assert.equal(elements.download.disabled,false);
assert.match(elements['trap-summary'].textContent,/16 Mission Reports/);
elements.china.checked=elements.gla.checked=false;elements.china.listeners.input();
assert.equal(elements.download.disabled,true);
elements['general-builders'].checked=false;elements['general-builders'].listeners.input();
assert.equal(elements.download.disabled,false);
assert.match(elements.yaml.textContent,/general_builder_unlocks: false/);
console.log('General builder option and capacity checks passed.');

for(const [id,key] of [['reveal-minimap','reveal_minimap'],['carpet-bomb','carpet_bomb'],['patriot-airdrop','patriot_airdrop']]) {
 elements[id].checked=true; elements[id].listeners.input();
 assert.match(elements.yaml.textContent,new RegExp(key+': true'));
 elements[id].checked=false; elements[id].listeners.input();
 assert.match(elements.yaml.textContent,new RegExp(key+': false'));
}
console.log('PASS: permanent ability toggles export YAML.');

// The fourth trap has the same zero-exclusion and relative weighting semantics.
elements['trap-enabled'].checked=true;
for(const id of ['power-weight','theft-weight','shutdown-weight'])elements[id].value='0';
elements['sell-weight'].value='7';elements['sell-weight'].listeners.input();
assert.equal(elements['sell-share'].textContent,'100.0% chance per trap.');
assert.match(elements.yaml.textContent,/sell_random_building_weight: 7/);

elements['trap-enabled'].checked=true;elements['sell-refund'].value='no_refund';elements['sell-refund'].listeners.input();assert.match(elements.yaml.textContent,/sell_building_refund: no_refund/);

// Point items have an opt-in budget and participate in pool capacity checks.
for(const id of ['usa','china','gla','general-builders','reveal-minimap','carpet-bomb','patriot-airdrop'])elements[id].checked=true;
elements['generals-powers'].listeners.input();
assert.match(elements.yaml.textContent,/progressive_generals_powers: false/);
assert.match(elements.yaml.textContent,/generals_point_items: 18/);
assert.equal(elements['generals-settings'].hidden,true);
elements['generals-powers'].checked=true;elements['generals-powers'].listeners.input();
assert.equal(elements['generals-settings'].hidden,false);
assert.equal(elements['generals-points'].disabled,false);
assert.equal(elements.download.disabled,true); // 18 points + other defaults cannot fit in 30 checks
for(let points=0;points<=28;points++){
 elements['generals-points'].value=String(points);elements.challenge.value='2';elements['generals-points'].listeners.input();
 assert.equal(elements.download.disabled,false);
 assert.match(elements.yaml.textContent,new RegExp('generals_point_items: '+points+'\\n'));
}
elements['generals-powers'].checked=false;elements.challenge.value='0';elements['generals-powers'].listeners.input();
assert.equal(elements.download.disabled,false);
assert.equal(elements['generals-points'].value,'28'); // disabled preferences preserved
console.log('PASS: progressive point toggle, default, 0-28 count, YAML and capacity.');

// All 110 reward combinations update actual YAML, previews and pool capacity.
for(const id of ['usa','china','gla'])elements[id].checked=true;
elements['trap-enabled'].checked=true;elements['trap-percent'].value='50';
elements.challenge.value='0';
for(let mission=1;mission<=10;mission++)for(let set=0;set<=10;set++){
 elements['mission-checks'].value=String(mission);elements['set-checks'].value=String(set);elements['mission-checks'].listeners.input();
 const total=15*mission+3*set;
 assert.equal(elements.summary.textContent,total+' total checks (including set bonuses)');
 assert.equal(elements['check-total'].textContent,String(total));
 assert.equal(elements['story-check-total'].textContent,String(15*mission));
 assert.equal(elements['challenge-check-total'].textContent,'0');
 assert.equal(elements['set-check-total'].textContent,String(3*set));
 assert.equal(elements.download.disabled,total<17);
 assert.match(elements.yaml.textContent,new RegExp('mission_completion_checks: '+mission+'\\n'));
 assert.match(elements.yaml.textContent,new RegExp('set_completion_checks: '+set+'\\n'));
 const left=Math.max(0,total-17),traps=Math.floor(left/2);
 assert.match(elements['trap-summary'].textContent,new RegExp(traps+' traps and '+(left-traps)+' Mission Reports'));
}
console.log('PASS: all 110 check-count combinations, YAML, total checks and filler capacity.');

// A random challenge may contain seven or eight missions; specific picks narrow the range.
elements['mission-checks'].value='1';elements['set-checks'].value='5';elements.challenge.value='1';elements.exclude.checked=false;
elements.challenge.listeners.input();
assert.equal(elements['check-total'].textContent,'42-43');
assert.equal(elements['challenge-check-total'].textContent,'7-8');
assert.equal(elements['set-check-total'].textContent,'20');
assert.match(elements['check-preview-note'].textContent,/Range shown/);
elements.start10.checked=true;elements.start10.listeners.input();
assert.equal(elements['check-total'].textContent,'43');
assert.equal(elements['challenge-check-total'].textContent,'8');
elements.exclude.checked=true;elements.exclude.listeners.input();
assert.equal(elements['check-total'].textContent,'41');
elements.start11.checked=true;elements.start11.listeners.input();
assert.equal(elements['check-total'].textContent,'--');
assert.match(elements['check-preview-note'].textContent,/valid campaign/);
for(let i=0;i<12;i++)elements['start'+i].checked=false;
elements.exclude.checked=false;elements.challenge.value='9';elements.challenge.listeners.input();
assert.equal(elements['check-total'].textContent,'140');
assert.equal(elements['challenge-check-total'].textContent,'65');
for(const id of ['usa','china','gla'])elements[id].checked=false;
elements.challenge.value='0';elements.challenge.listeners.input();
assert.equal(elements['check-total'].textContent,'0');
assert.match(elements['check-preview-note'].textContent,/Select a story/);
console.log('PASS: live total breakdown, random range, fixed generals, exclusions and invalid selection.');

// New gameplay options update previews and free precollected slots.
for (const id of ['usa','china','gla','general-builders','reveal-minimap','carpet-bomb','patriot-airdrop']) elements[id].checked=true;
for(let i=0;i<12;i++)elements['start'+i].checked=false;
for(let i=0;i<15;i++)elements['unlock'+i].checked=false;
elements.challenge.value='0';elements.exclude.checked=false;
elements['mission-checks'].value='1';elements['set-checks'].value='5';
elements['generals-powers'].checked=false;elements.cash.value='0';
elements['trap-enabled'].checked=false;elements.startcount.value='1';
elements['starting-points'].value='0';elements['goal-final'].value='usa';elements['victory-goal'].value='all_sets';
context.update();
assert.match(elements['trap-summary'].textContent,/13 Mission Reports/);
elements.unlock0.checked=true;elements.unlock12.checked=true;context.update();
assert.match(elements.yaml.textContent,/starting_builders: \["USA Dozer"\]/);
assert.match(elements.yaml.textContent,/starting_abilities: \["Reveal Minimap"\]/);
assert.match(elements['trap-summary'].textContent,/15 Mission Reports/);
assert.equal(elements['check-total'].textContent,'30');
elements['reveal-minimap'].checked=false;context.update();assert.equal(elements.download.disabled,true);
elements['reveal-minimap'].checked=true;elements['starting-points'].value='2';context.update();assert.equal(elements.download.disabled,true);
elements['generals-powers'].checked=true;elements['generals-points'].value='2';context.update();assert.equal(elements.download.disabled,false);
assert.match(elements.yaml.textContent,/starting_generals_points: 2/);
elements['victory-goal'].value='set_count';elements['goal-sets'].value='4';context.update();assert.equal(elements.download.disabled,true);
elements['goal-sets'].value='2';context.update();assert.equal(elements.download.disabled,false);
elements['victory-goal'].value='final_mission';elements['goal-final'].value='challenge_7';context.update();assert.equal(elements.download.disabled,true);
elements.challenge.value='1';context.update();assert.equal(elements.download.disabled,false);
assert.equal(elements['check-total'].textContent,'43'); // Infantry has eight battles, forced into selection.
for(const [id,value,key] of [['power-seconds',90,'power_outage_seconds'],['shutdown-seconds',45,'production_shutdown_seconds'],['theft-percent',40,'cash_theft_percent'],['cooldown-percent',250,'ability_cooldown_percent'],['death-grace',60,'death_link_grace_seconds']]){
 elements[id].value=String(value);context.update();assert.match(elements.yaml.textContent,new RegExp(key+': '+value));
}
console.log('PASS: starting unlock capacity, configurable goals, forced final general, strength, cooldown and grace YAML.');

// Grace is opt-in and its duration controls follow both switches.
assert.equal(elements['death-grace-enabled'].checked,false);
context.update();
assert.equal(elements['death-grace-settings'].hidden,true);
assert.equal(elements['death-grace-settings'].disabled,true);
assert.match(elements.yaml.textContent,/death_link_grace_enabled: false/);
elements.deathlink.checked=true;elements['death-grace-enabled'].checked=true;context.update();
assert.equal(elements['death-grace-settings'].hidden,false);
assert.equal(elements['death-grace'].disabled,false);
assert.match(elements.yaml.textContent,/death_link_grace_enabled: true/);
elements.deathlink.checked=false;context.update();
assert.equal(elements['death-grace-settings'].disabled,true);
console.log('PASS: explicit opt-in grace switch and dependent controls.');

// Weights apply only after trap allocation; fixed item counts remain reserved.
assert.equal(elements['report-filler'].value,'50');
assert.equal(elements['supply-filler'].value,'0');
assert.equal(elements['reinforcement-filler'].value,'0');
elements['victory-goal'].value='all_sets';elements.challenge.value='0';
elements['generals-powers'].checked=false;elements['starting-points'].value='0';
for(let i=0;i<15;i++)elements['unlock'+i].checked=false;
elements['trap-enabled'].checked=true;elements['trap-percent'].value='50';
elements['report-filler'].value='0';elements['supply-filler'].value='25';elements['reinforcement-filler'].value='75';
context.update();
assert.equal(elements.download.disabled,false);
assert.equal(elements['check-total'].textContent,'30');
assert.match(elements['trap-summary'].textContent,/6 traps and 7 non-trap filler slots/);
assert.match(elements['filler-summary'].textContent,/Supply Drop 1.8, Reinforcements 5.3/);
assert.match(elements.yaml.textContent,/supply_drop_weight: 25/);
assert.match(elements.yaml.textContent,/reinforcements_weight: 75/);
assert.match(elements.yaml.textContent,/mission_report_weight: 0/);
assert.doesNotMatch(elements.yaml.textContent,/\n  (supply_drops|reinforcements|progress_tracker):/);
elements['supply-filler'].value=elements['reinforcement-filler'].value='0';context.update();
assert.equal(elements.download.disabled,true);
elements['trap-percent'].value='100';context.update();assert.equal(elements.download.disabled,false);
assert.match(elements['filler-summary'].textContent,/No slots remain/);
elements['trap-enabled'].checked=false;context.update();assert.equal(elements.download.disabled,true);
elements['supply-filler'].value='50';context.update();assert.equal(elements.download.disabled,false);
assert.match(elements['trap-summary'].textContent,/0 traps and 13 non-trap filler slots/);
console.log('PASS: useful filler defaults, ratios, YAML, cash count, trap priority and zero-weight validation.');

// Goal controls must respond to real input/change events and omit inactive YAML.
assert.equal(elements['progress-tracker'], undefined);
assert.equal(elements.supplies, undefined);
assert.equal(elements.reinforcements, undefined);
assert.equal(elements.cash.value, '0');
for(const goal of ['set_count','final_mission','all_sets','set_count']){
 elements['victory-goal'].value=goal;
 elements['victory-goal'].listeners.change();
 assert.equal(elements['goal-sets'].disabled, goal!=='set_count');
 assert.equal(elements['goal-sets-settings'].hidden, goal!=='set_count');
 assert.equal(elements['goal-final'].disabled, goal!=='final_mission');
 assert.equal(elements['goal-final-settings'].hidden, goal!=='final_mission');
 assert.equal(/\n  goal_set_count:/.test(elements.yaml.textContent), goal==='set_count');
 assert.equal(/\n  goal_final_set:/.test(elements.yaml.textContent), goal==='final_mission');
}
console.log('PASS: conditional goal controls, YAML omission, always-on tracker and retained cash selector.');

// The fourth permanent ability reserves one pool slot, or is precollected.
elements['victory-goal'].value='all_sets';elements['emergency-repair'].checked=true;
context.update();assert.match(elements.yaml.textContent,/emergency_repair: true/);
const repairBefore=elements['trap-summary'].textContent;
elements.unlock15.checked=true;context.update();
assert.match(elements.yaml.textContent,/starting_abilities: .*Emergency Repair/);
assert.notEqual(elements['trap-summary'].textContent,repairBefore);
elements['emergency-repair'].checked=false;context.update();
assert.equal(elements.download.disabled,true);
elements.unlock15.checked=false;context.update();assert.equal(elements.download.disabled,false);
console.log('PASS: Emergency Repair toggle, starting unlock and live pool capacity.');

for(const id of ['report-filler','supply-filler','reinforcement-filler'])elements[id].value='0';
for(const [id,key] of [['production-filler','production_surge_weight'],['construction-filler','construction_boost_weight']]){
 elements[id].value='50';context.update();
 assert.equal(elements.download.disabled,false);
 assert.match(elements.yaml.textContent,new RegExp(key+': 50'));
 assert.match(elements[id+'-share'].textContent,/100/);
 elements[id].value='0';context.update();
 assert.equal(elements.download.disabled,true);
}
console.log('PASS: both boost weights independently enable filler generation and export YAML.');
