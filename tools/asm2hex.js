function hexToAsm(hexInstruction) {
  // Validate hex input: must be 8 hexadecimal digits
  if (!/^[0-9a-fA-F]{8}$/.test(hexInstruction)) {
    return 'Invalid hex: must be 8 hexadecimal digits';
  }

  // Convert hex to 32-bit integer
  const instruction = parseInt(hexInstruction, 16);

  // Extract fields for MOVZ
  const sf = (instruction >> 31) & 1; // Bit 31
  const opc = (instruction >> 29) & 3; // Bits 30-29
  const movzBits = (instruction >> 23) & 0x3f; // Bits 28-23
  const hw = (instruction >> 21) & 3; // Bits 22-21
  const imm16 = (instruction >> 5) & 0xffff; // Bits 20-5
  const rd = instruction & 0x1f; // Bits 4-0

  // Check if it's a MOVZ instruction (32-bit, no shift)
  if (sf !== 0 || opc !== 2 || movzBits !== 0x25 || hw !== 0) {
    return 'Not a valid 32-bit MOVZ instruction with no shift';
  }

  // Format the assembly instruction
  const immediateHex = imm16.toString(16).toLowerCase();
  return `mov w${rd}, #0x${immediateHex}`;
}

function asmToHex(asmInstruction) {
  // Parse the instruction (e.g., "mov w2, #0x5a0")
  const match = asmInstruction.match(/mov\s+w(\d+),\s*#0x([0-9a-fA-F]+)/i);
  if (!match) {
    return 'Invalid instruction format. Use: mov w<reg>, #0x<imm>';
  }

  const register = parseInt(match[1], 10); // e.g., 2 for w2
  const immediate = parseInt(match[2], 16); // e.g., 0x5a0

  // Validate inputs
  if (register < 0 || register > 31) {
    return 'Register must be between 0 and 31';
  }
  if (immediate < 0 || immediate > 0xffff) {
    return 'Immediate value must be 0 to 0xffff for MOVZ';
  }

  // MOVZ encoding for 32-bit register (sf = 0)
  const sf = 0; // Bit 31: 0 for 32-bit
  const opc = 2; // Bits 30-29: 10 for MOVZ
  const movzBits = 0x25; // Bits 28-23: 100101 for MOVZ
  const hw = 0; // Bits 22-21: 00 (no shift)
  const imm16 = immediate; // Bits 20-5: 16-bit immediate
  const rd = register; // Bits 4-0: destination register

  // Construct 32-bit instruction
  const instruction =
    (sf << 31) |
    (opc << 29) |
    (movzBits << 23) |
    (hw << 21) |
    (imm16 << 5) |
    rd;

  // Convert to 8-digit hexadecimal (padded with leading zeros)
  return instruction.toString(16).padStart(8, '0').toLowerCase();
}

// console.log(asmToHex('mov w2, #0x5a0')); // Outputs: "528005a2"
// console.log(asmToHex('mov w0, #0x1234')); // Outputs: "52824680"

// Test hexToAsm
console.log(hexToAsm('02B48052')); // Outputs: "Not a valid 32-bit MOVZ instruction with no shift"
