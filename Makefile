VM ?= lifeos-vm

.PHONY: sync restart logs dev

sync:
	rsync -av --exclude node_modules --exclude .venv --exclude __pycache__ \
		apps/host packages/ infra/ $(VM):~/lifeos/

restart: sync
	ssh $(VM) 'systemctl --user restart lifeos-host'

logs:
	ssh $(VM) 'journalctl --user -u lifeos-host -f'

dev:
	pnpm --filter glassbox dev
