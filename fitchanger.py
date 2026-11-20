import struct
from typing import Optional


def crc16_fit(data: bytes) -> int:
  crc_table = [
      0x0000,
      0xCC01,
      0xD801,
      0x1400,
      0xF001,
      0x3C00,
      0x2800,
      0xE401,
      0xA001,
      0x6C00,
      0x7800,
      0xB401,
      0x5000,
      0x9C01,
      0x8801,
      0x4400,
  ]
  crc = 0
  for byte in data:
    tmp = crc_table[crc & 0xF]
    crc = (crc >> 4) & 0x0FFF
    crc = crc ^ tmp ^ crc_table[byte & 0xF]
    tmp = crc_table[crc & 0xF]
    crc = (crc >> 4) & 0x0FFF
    crc = crc ^ tmp ^ crc_table[(byte >> 4) & 0xF]
  return crc


def patch_fit_device(
    input_path: str,
    output_path: str,
    manufacturer_id: int,
    product_id: int,
    serial_number: Optional[int] = None,
  ) -> None:
  with open(input_path, "rb") as f:
    buf = bytearray(f.read())

  if len(buf) < 12:
    raise ValueError("Invalid FIT file: file is too short")

  header_size = buf[0]
  data_size = struct.unpack("<I", buf[4:8])[0]
  end_data = header_size + data_size
  if header_size < 12 or header_size > len(buf):
    raise ValueError("Invalid FIT file: invalid header size")
  if end_data > len(buf):
    raise ValueError("Invalid FIT file: truncated data section")
  if len(buf) < end_data + 2:
    raise ValueError("Invalid FIT file: missing or truncated CRC")

  local_defs = {}
  pos = header_size

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
      if pos + defn["size"] > end_data:
        raise ValueError("Invalid FIT file: truncated data record")
      # 0 = file_id, 23 = device_info
      if defn["global"] in (0, 23):
        # On vérifie si c'est l'appareil principal (device_index == 0 ou absent dans file_id)
        is_main_device = True
        if defn["global"] == 23:
          for f_num, off, f_size in defn["fields"]:
            if f_num == 0:
              if f_size == 0 or pos + off + f_size > end_data:
                raise ValueError("Invalid FIT file: truncated device index field")
              if buf[pos + off] != 0:  # device_index != 0 (ex: capteur ceinture/puissance)
                is_main_device = False
                break

        if is_main_device:
          for f_num, off, f_size in defn["fields"]:
            if pos + off + f_size > end_data:
              raise ValueError("Invalid FIT file: truncated data field")
            if f_num == 1 and f_size == 2:  # manufacturer
              struct.pack_into(
                  defn["endian"] + "H", buf, pos + off, manufacturer_id
              )
            elif (
                defn["global"] == 0 and f_num == 2 and f_size == 2
            ):  # product in file_id
              struct.pack_into(
                  defn["endian"] + "H", buf, pos + off, product_id
              )
            elif (
                defn["global"] == 23 and f_num == 4 and f_size == 2
            ):  # product in device_info
              struct.pack_into(
                  defn["endian"] + "H", buf, pos + off, product_id
              )
            elif (
                defn["global"] == 0 and f_num == 7 and f_size == 4 and serial_number is not None
            ):  # serial_number in file_id
              struct.pack_into(
                  defn["endian"] + "I", buf, pos + off, serial_number
              )
            elif (
                defn["global"] == 23 and f_num == 3 and f_size == 4 and serial_number is not None
            ):  # serial_number in device_info
              struct.pack_into(
                  defn["endian"] + "I", buf, pos + off, serial_number
              )
      pos += defn["size"]

  new_crc = crc16_fit(buf[:end_data])
  struct.pack_into("<H", buf, end_data, new_crc)

  with open(output_path, "wb") as f:
    f.write(buf)
