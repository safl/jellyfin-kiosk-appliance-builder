VARIANT ?= dk
DISK_IMAGE = $(HOME)/system_imaging/disk/jkab-$(VARIANT)-x86_64.qcow2

.DEFAULT_GOAL := help

.PHONY: help deps build test interactive clean

help:
	@echo "JKAB - Jellyfin Kiosk Appliance Builder"
	@echo ""
	@echo "Targets:"
	@echo "  deps     Install build dependencies (cijoe via pipx)"
	@echo "  build       Build the appliance disk image"
	@echo "  test        Run test suite on a built image"
	@echo "  interactive Boot the appliance in QEMU with SPICE display"
	@echo "  clean    Remove build artifacts"
	@echo ""
	@echo "Variant: $(VARIANT) (override with VARIANT=us, etc.)"
	@echo "Output: $(DISK_IMAGE)"

deps:
	pipx install cijoe
	pipx inject cijoe pytest --include-apps
	pipx inject cijoe pytest-random-order pytest-reportlog
	pipx ensurepath

build:
	cijoe tasks/build.yaml --monitor -c configs/$(VARIANT).toml

test:
	cijoe tasks/test.yaml --monitor -c configs/$(VARIANT).toml

interactive:
	cijoe tasks/run.yaml --monitor -c configs/$(VARIANT).toml

clean:
	rm -rf cijoe-output cijoe-archive
	rm -f $(DISK_IMAGE) $(DISK_IMAGE).sha256
