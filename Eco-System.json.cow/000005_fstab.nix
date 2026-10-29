# /etc/nixos/Eco-System/hosts/laptop/fstab.nix
{ config, lib, pkgs, modulesPath, ... }:

{
  # ==========================================
  # IMPORT: Hardware-Erkennung
  # ==========================================
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
  ];

  # ==========================================
  # LUKS-VERSCHLÜSSELUNG (Hauptpartition)
  # ==========================================
  boot.initrd.luks.devices."luks-8f434902-3496-446b-908f-e0f4010a434b" = {
    device = "/dev/disk/by-uuid/8f434902-3496-446b-908f-e0f4010a434b";
  };

  # ==========================================
  # LUKS-VERSCHLÜSSELUNG (SWAP-Partition – separat!)
  # ==========================================
  boot.initrd.luks.devices."luks-70b818df-e3e5-401c-99fd-41188984daa4" = {
    device = "/dev/disk/by-uuid/70b818df-e3e5-401c-99fd-41188984daa4";
  };

  # ==========================================
  # FILESYSTEMS (Mounts)
  # ==========================================
  fileSystems = {
    "/" = {
      device  = "/dev/mapper/luks-8f434902-3496-446b-908f-e0f4010a434b";
      fsType  = "btrfs";
      options = [ "compress=zstd:1" ];
    };

    "/home" = {
      device  = "/dev/mapper/luks-8f434902-3496-446b-908f-e0f4010a434b";
      fsType  = "btrfs";
      options = [ "subvol=home" "compress=zstd:1" ];
    };

    "/nix" = {
      device  = "/dev/mapper/luks-8f434902-3496-446b-908f-e0f4010a434b";
      fsType  = "btrfs";
      options = [ "subvol=nix" "compress=zstd:1" "noatime" ];
    };

    "/boot" = {
      device  = "/dev/disk/by-uuid/E762-C728";
      fsType  = "vfat";
      options = [ "fmask=0077" "dmask=0077" ];
    };
  };

  # ==========================================
  # SWAP (separate verschlüsselte Partition)
  # ==========================================
  swapDevices = [
    { device = "/dev/mapper/luks-70b818df-e3e5-401c-99fd-41188984daa4"; }
  ];
}
