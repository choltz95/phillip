import os
import sys
from argparse import ArgumentParser
import subprocess

parser = ArgumentParser()

parser.add_argument('path', type=str, help="path to experiment")
parser.add_argument('--dry_run', action='store_true', help="don't start jobs")
parser.add_argument('--init', action='store_true', help="initialize model")
parser.add_argument('--trainer', type=str, help='trainer IP address')
parser.add_argument('--local', action='store_true', help="run locally")
parser.add_argument('--agents', type=int, help="number of agents to run")
parser.add_argument('--log_agents', action='store_true', help='log agent outputs')

args = parser.parse_args()

import json
with open(args.path + 'params') as f:
  params = json.load(f)

run_trainer = True
run_agents = True

if args.local:
  agent_dump = "localhost"
  trainer_dump = "127.0.0.1"
else: # running on openmind
  if args.trainer:
    agent_dump = "172.16.24.%s" % args.trainer
    run_trainer = False
  else:
    trainer_dump = "ib0"
    run_agents = False

if args.dry_run:
  print("NOT starting jobs:")
else:
  print("Starting jobs:")

# init model for the first time
if args.init:
  import RL
  model = RL.Model(mode=RL.Mode.TRAIN, **params['train'])
  model.init()
  model.save()

if not os.path.exists("slurm_logs"):
    os.makedirs("slurm_logs")

if not os.path.exists("slurm_scripts"):
    os.makedirs("slurm_scripts")

def launch(name, command, cpus=2, mem=1000, gpu=False, log=True, qos=None, array=None):
  if args.dry_run:
    print(command)
    return
  
  if args.local:
    if array is None:
      array = 1
    for i in range(array):
      kwargs = {}
      for s in ['out', 'err']:
        kwargs['std' + s] = open("slurm_logs/%s_%d.%s" % (name, i, s), 'w') if log else subprocess.DEVNULL
      subprocess.Popen(command.split(' '), **kwargs)
    return

  slurmfile = 'slurm_scripts/' + name + '.slurm'
  with open(slurmfile, 'w') as f:
    f.write("#!/bin/bash\n")
    f.write("#SBATCH --job-name " + name + "\n")
    if log:
      f.write("#SBATCH --output slurm_logs/" + name + "_%a.out\n")
      f.write("#SBATCH --error slurm_logs/" + name + "_%a.err\n")
    else:
      f.write("#SBATCH --output /dev/null")
      f.write("#SBATCH --error /dev/null")
    f.write("#SBATCH -c %d\n" % cpus)
    f.write("#SBATCH --mem %d\n" % mem)
    f.write("#SBATCH --time 7-0\n")
    #f.write("#SBATCH --cpu_bind=verbose,cores\n")
    #f.write("#SBATCH --cpu_bind=threads\n")
    if gpu:
      f.write("#SBATCH --gres gpu:titan-x:1\n")
      #f.write("#SBATCH --gres gpu:1\n")
    if qos:
      f.write("#SBATCH --qos %s\n" % qos)
    if array:
      f.write("#SBATCH --array=1-%d\n" % array)
    f.write(command)

  #command = "screen -S %s -dm srun --job-name %s --pty singularity exec -B $OM_USER/phillip -B $HOME/phillip/ -H ../home phillip.img gdb -ex r --args %s" % (name[:10], name, command)
  os.system("sbatch " + slurmfile)

if run_trainer:
  train_name = "trainer_" + params['train']['name']
  train_command = "python3 -u train.py --load " + args.path
  train_command += " --dump " + trainer_dump
  
  launch(train_name, train_command,
    gpu=True,
    #qos='tenenbaum',
    mem=16000
  )

enemies = 'easy'
if 'enemies' in params:
  enemies = params['enemies']

with open('enemies/' + enemies) as f:
  enemies = json.load(f)

agents = 1
if params['agents']:
  agents = params['agents']
if args.agents:
  agents = args.agents

print("Using %d agents" % agents)
agents //= len(enemies)

if run_agents:
  agent_count = 0
  agent_command = "python3 -u run.py --load " + args.path
  agent_command += " --dump " + agent_dump
  if not args.local:
    agent_command += " --cpu_thread"

  for enemy in enemies:
    command = agent_command + " --enemy "
    if enemy == "self":
      command += args.path
    else:
      command += "agents/%s/" % enemy

    agent_name = "agent_%d_%s" % (agent_count, params['agent']['name'])
    launch(agent_name, command,
      log=args.log_agents,
      qos='use-everything',
      array=agents
    )
    agent_count += 1

