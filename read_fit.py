import argparse
import struct
from pathlib import Path
from typing import Optional, Tuple


def read_fit_device(
    filepath: str,
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
  """Lit manufacturer, product et serial_number depuis un fichier FIT."""
  with open(filepath, "rb") as f:
    buf = f.read()

  if len(buf) < 8:
    raise ValueError("fichier FIT trop court : en-tête incomplet")

  header_size = buf[0]
  if header_size < 12 or header_size > len(buf):
    raise ValueError(f"taille d'en-tête FIT invalide : {header_size}")

  data_size = struct.unpack("<I", buf[4:8])[0]
  end_data = header_size + data_size
  if end_data > len(buf):
    raise ValueError("fichier FIT tronqué : données incomplètes")

  local_defs = {}
  pos = header_size
  manufacturer_id = None
  product_id = None
  serial_number = None
  file_id_manufacturer = None
  file_id_product = None
  device_manufacturer = None
  device_product = None
  device_serial_number = None

  while pos < end_data:
    if pos >= end_data:
      break
    rh = buf[pos]
    pos += 1
    if rh & 0x80:
      defn = local_defs.get((rh >> 5) & 0x03)
      if defn is None:
        break
      pos += defn["size"]
      if pos > end_data:
        break
      continue
    is_def = (rh & 0x40) != 0
    has_dev = (rh & 0x20) != 0
    l_type = rh & 0x0F

    if is_def:
      if pos + 5 > end_data:
        break
      endian = "<" if buf[pos + 1] == 0 else ">"
      g_num = struct.unpack(endian + "H", buf[pos + 2 : pos + 4])[0]
      n_fields = buf[pos + 4]
      pos += 5
      fields, total_size = [], 0
      for _ in range(n_fields):
        if pos + 3 > end_data:
          break
        fields.append((buf[pos], total_size, buf[pos + 1]))
        total_size += buf[pos + 1]
        pos += 3
      if len(fields) != n_fields:
        break
      if has_dev:
        if pos >= end_data:
          break
        pos += 1 + buf[pos] * 3
        if pos > end_data:
          break
      local_defs[l_type] = {
          "global": g_num,
          "endian": endian,
          "fields": fields,
          "size": total_size,
      }
    else:
      defn = local_defs.get(l_type)
      if defn is None:
        break

      if defn["global"] in (0, 23):
        is_main_device = True
        if defn["global"] == 23:
          for f_num, off, f_size in defn["fields"]:
            if f_num == 0 and pos + off < end_data:
              if buf[pos + off] != 0:
                is_main_device = False
              break

        if not is_main_device:
          pos += defn["size"]
          continue

        for f_num, off, f_size in defn["fields"]:
          if pos + off + f_size > end_data:
            continue
          if defn["global"] == 0 and f_num == 1 and f_size == 2:
            file_id_manufacturer = struct.unpack(
                defn["endian"] + "H",
                buf[pos + off : pos + off + 2],
            )[0]
          elif defn["global"] == 0 and f_num == 2 and f_size == 2:
            file_id_product = struct.unpack(
                defn["endian"] + "H",
                buf[pos + off : pos + off + 2],
            )[0]
          elif defn["global"] == 23 and f_num == 1 and f_size == 2:
            device_manufacturer = struct.unpack(
                defn["endian"] + "H",
                buf[pos + off : pos + off + 2],
            )[0]
          elif defn["global"] == 23 and f_num == 4 and f_size == 2:
            device_product = struct.unpack(
                defn["endian"] + "H",
                buf[pos + off : pos + off + 2],
            )[0]
          elif defn["global"] == 23 and f_num == 3 and f_size == 4:
            device_serial_number = struct.unpack(
                defn["endian"] + "I",
                buf[pos + off : pos + off + 4],
            )[0]
      pos += defn["size"]

  manufacturer_id = device_manufacturer
  if manufacturer_id is None:
    manufacturer_id = file_id_manufacturer

  product_id = device_product
  if product_id is None:
    product_id = file_id_product

  serial_number = device_serial_number
  return manufacturer_id, product_id, serial_number


def main() -> None:
  parser = argparse.ArgumentParser(
      description="Lit les identifiants appareil principaux depuis un fichier FIT.",
  )
  parser.add_argument("fit_file", type=Path, help="Chemin du fichier .fit")
  args = parser.parse_args()

  if not args.fit_file.is_file():
    parser.error(f"fichier introuvable : {args.fit_file}")

  manufacturer_id, product_id, serial_number = read_fit_device(str(args.fit_file))
  print(f"manufacturer_id: {manufacturer_id}")
  print(f"product_id:      {product_id}")
  print(f"serial_number:   {serial_number}")


if __name__ == "__main__":
  main()