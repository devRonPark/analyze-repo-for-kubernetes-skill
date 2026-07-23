# Configuration Timing

Classify each major configuration name by when it takes effect.

## Application Phase Values

- **build-time:** embedded while compiling or creating an image or static bundle; changing it requires a rebuild
- **deployment-time:** selected or rendered by deployment tooling before workload creation
- **process-start:** read when the process starts; changing it requires a restart or rollout
- **runtime:** reread while the process is running without restart
- **administrative-time:** applied through an external control plane or manual administrative action
- **Unknown:** repository evidence does not establish the phase

## Required Fields

For each important configuration include:

- name
- component
- purpose
- Application Phase
- source or injection method
- change effect
- secret classification without revealing values
- evidence status

Do not assume every environment variable is process-start configuration. Frontend variables such as Vite build arguments are often build-time settings embedded into static assets.
