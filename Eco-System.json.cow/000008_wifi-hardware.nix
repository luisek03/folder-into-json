# /etc/nixos/Eco-System/hosts/laptop/wifi-hardware.nix
{ config, pkgs, lib, ... }:

{
  # ==========================================
  # WLAN-HARDWARE: REALTEK RTL8821CE
  # ==========================================
  # Karte:     RTL8821CE (PCIe, 1x1 802.11ac, 80 MHz)
  # Treiber:   rtw88_8821ce
  # Firmware:  linux-firmware-20260916 (aktuell)
  # Regulatory: DE (korrekt)
  #
  # Bekannte Probleme des rtw88-Treibers:
  #   1. ASPM L1   → PCIe-Schlafzustand, RX-DMA wird langsam
  #   2. Deep LPS  → 32-kHz-Tiefschlaf, PCIe-Timeouts
  #   3. power_save → MAC-Layer-Schlaf, Durchsatz-Einbrüche
  #
  # Ziel: ~200-250 Mbit/s TCP-Durchsatz (wie unter Fedora).
  # ==========================================

  # ==========================================
  # WERKZEUGE
  # ==========================================
  # lib.mkAfter hängt an die gemergte systemPackages-Liste an,
  # ohne die Definitionen aus profile/base + profile/luis-eco zu
  # überschreiben. Kein Konflikt, keine Priorität nötig.
  # ==========================================
  environment.systemPackages = with pkgs; [
    iw          # Interface-Diagnose (iw dev, iw link)
    pciutils    # lspci für Hardware-Identifikation
  ];

  # ==========================================
  # POWER-SAVE DEAKTIVIEREN (802.11-Ebene)
  # ==========================================
  # Setzt power_save off beim Boot auf dem WLAN-Interface.
  # Betrifft nur den MAC-Layer. ASPM und Deep LPS werden
  # separat per Modul-Optionen gesteuert (siehe unten).
  # ==========================================
  systemd.services.disable-wifi-powersave = {
    description = "Disable WiFi power saving";
    after       = [ "network.target" "systemd-udev-settle.service" ];
    wantedBy    = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = ''
      INTERFACE=$(${pkgs.gawk}/bin/awk '$1=="Interface" {print $2; exit}' <(${pkgs.iw}/bin/iw dev))
      if [ -n "$INTERFACE" ]; then
        ${pkgs.iw}/bin/iw dev "$INTERFACE" set power_save off
        echo "WiFi power save disabled for $INTERFACE"
      else
        echo "No WiFi interface found"
      fi
    '';
  };

  # ==========================================
  # RTL8821CE: ASPM UND DEEP LPS DEAKTIVIEREN
  # ==========================================
  # Modul-Optionen für den rtw88-Treiber.
  #
  # disable_aspm=1      → verhindert PCIe-L1-Schlafzustand
  # disable_lps_deep=1  → verhindert 32-kHz-Firmware-Schlaf
  #
  # Wichtig: Wirkt erst nach KALTSTART, nicht nach normalem
  # Reboot. Der PCIe-Link-Zustand überlebt einen warmen Reboot.
  #   sudo shutdown -h now
  # ==========================================
  boot.extraModprobeConfig = ''
    options rtw88_pci disable_aspm=1
    options rtw88_core disable_lps_deep=1
  '';

  # ==========================================
  # IWD STATT WPA_SUPPLICANT
  # ==========================================
  # Fedora nutzt iwd als WLAN-Backend. iwd hat eine andere
  # Rate-Control-Logik, die bei der RTL8821CE deutlich mehr
  # Durchsatz bringt (Erfahrungswert: bis zu 2x).
  #
  # NetworkManager delegiert das WLAN-Management an iwd.
  # ==========================================
  networking.networkmanager.wifi.backend = "iwd";
  networking.wireless.iwd.enable         = true;
}
