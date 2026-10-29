# /etc/nixos/Eco-System/hosts/laptop/kernel-modules.nix
{ config, lib, pkgs, modulesPath, ... }:

{
  # ==========================================
  # IMPORT: Hardware-Erkennung (für Kernel-Module)
  # ==========================================
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")

    # Kernel-System: Options + LTS-Fallback.
    # Muss immer importiert werden, damit mySystem.customKernel
    # existiert – auch wenn kein Custom-Kernel aktiv ist.
    ../../modules/system/kernel

    # Konkreter Kernel: v3 + thinlto + bore (lokaler Build via Override).
    # Alternativen (immer NUR eine wählen):
    #   ../../modules/system/kernel/cachyos               # v1 aus Cache
       ../../modules/system/kernel/cachyos/lto-v3.nix    # v3 thinlto bore
  ];

  # ==========================================
  # KERNEL-MODULE (Hardware-spezifisch)
  # ==========================================
  # WICHTIG: Kein lib.mkForce hier!
  #
  # NixOS ergänzt diese Listen automatisch:
  #   - boot.initrd.luks.devices.*  → dm-crypt, dm-mod, aes, sha256, ...
  #   - boot.initrd.availableKernelModules → udev, usb, nvme, ...
  #
  # lib.mkForce würde diese automatischen Ergänzungen ÜBERSCHREIBEN
  # (nicht mergen) → LUKS-Module fehlen in der initrd → Root-Partition
  # nicht entschlüsselbar → "Failed to start Find NixOS closure".
  #
  # Normale Zuweisung (Prio 100) reicht: NixOS merged seine Module
  # mit dieser Liste, sodass sowohl die hardware-spezifischen als
  # auch die sicherheitskritischen LUKS-Module in der initrd landen.
  # ==========================================
  boot.initrd.availableKernelModules = [
    "nvme"
    "xhci_pci"
    "usb_storage"
    "sd_mod"
  ];
  boot.initrd.kernelModules    = [ ];
  boot.kernelModules           = [ "kvm-amd" ];
  boot.extraModulePackages     = [ ];

  # ==========================================
  # CACHYOS-KERNEL (Laptop-spezifisch)
  # ==========================================
  # Dieser Laptop hat einen AMD Ryzen 5 7520U (Zen 2).
  #
  # Der aktive Kernel wird durch den Import oben bestimmt –
  # nicht mehr über mySystem.cachyosKernel-Optionen.
  #
  # Für den Laptop: Zen 2 unterstützt x86-64-v3 vollständig.
  # v3 + thinlto + bore ist der Kompromiss aus Kompatibilität
  # und Leistung. v1 (aus Cache) wäre die schnellere, aber
  # generischere Variante. znver2 (lto-zen.nix) wäre die
  # spezifischere, aber langsamer zu bauende Variante.
  # ==========================================
  mySystem.customKernel.enable = true;

  system.nixos.tags = [ "lto" "v3" "bore" ];

  # ==========================================
  # ALLGEMEINE HARDWARE-OPTIMIERUNG
  # ==========================================

  # powertop --auto-tune verringert den energie verbauch bei gleicher leistung, bzw es  kann zum folgende bugs kommen, USB-Autosuspend (der häufigste Störfaktor), PCIe ASPM, Systemweite Verlangsamung oder.
  # "Buggy Hardware": Ein grundsätzliches Problem ist, dass die Einstellungen zwar nach Spezifikation sicher sein sollten, in der Praxis aber fehlerhafte Hardware oder Treiber dazu führen können, dass die Energiesparmodi nicht korrekt funktionieren und das System instabil wird.

  #powerManagement.powertop.enable = true;           # Deaktiviert beißt sich mit Energieplan der Wifi-Hardwaren.nix.
  # Wifi-Hardware.nix hat ein höhere exisitentsberechtigung !!!
  #boot.kernelParams = [ "usbcore.autosuspend=30" ];



  # ==========================================
  # PLATTFORM & MICROCODE
  # ==========================================
  nixpkgs.hostPlatform = "x86_64-linux";

  # Firmware (WLAN, GPU, etc.) + AMD-Microcode.
  # Ohne explizites true bleibt updateMicrocode effektiv aus,
  # weil config.hardware.enableRedistributableFirmware sonst false ist.
  hardware.enableRedistributableFirmware = true;
  hardware.cpu.amd.updateMicrocode       = true;
}
