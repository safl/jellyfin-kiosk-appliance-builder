DISK_IMAGE = $(HOME)/system_imaging/disk/jkab-x86_64.qcow2

.DEFAULT_GOAL := help

.PHONY: help deps build clean

help:
	@echo "JKAB - Jellyfin Kiosk Appliance Builder"
	@echo ""
	@echo "Targets:"
	@echo "  deps     Install build dependencies (cijoe via pipx)"
	@echo "  build    Build the appliance disk image"
	@echo "  clean    Remove build artifacts"
	@echo ""
	@echo "Output: $(DISK_IMAGE)"

deps:
	pipx install cijoe

build:
	cijoe tasks/build.yaml --monitor -c configs/config.toml

clean:
	rm -rf cijoe-output cijoe-archive
	rm -f $(DISK_IMAGE) $(DISK_IMAGE).sha256
