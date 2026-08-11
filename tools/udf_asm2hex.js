function convertUdfToArm64MachineCode(instructions) {
    const result = [];
  
    for (const instruction of instructions) {
        // Ensure the instruction starts with "udf #"
        if (!instruction.trim().startsWith("udf #")) {
            throw new Error(`Invalid instruction format: ${instruction}. Expected "udf #<value>"`);
        }
  
        // Extract the immediate value (e.g., "#0xd70" or "#1440")
        const immediateStr = instruction.split("#")[1].trim();
        let immediate;
  
        // Parse hex (e.g., "0xd70") or decimal (e.g., "3440")
        if (immediateStr.startsWith("0x")) {
            immediate = parseInt(immediateStr.slice(2), 16);
        } else {
            immediate = parseInt(immediateStr, 10);
        }
  
        // Validate the immediate is a 16-bit value (0 to 0xFFFF)
        if (isNaN(immediate) || immediate < 0 || immediate > 0xFFFF) {
            throw new Error(`Immediate value out of range (0-65535): ${immediateStr}`);
        }
  
        // ARM64 udf encoding: 0000iiii (where iiii is the 16-bit immediate)
        const udfEncoding = immediate & 0xFFFF; // Mask to 16 bits
        const hexEncoding = udfEncoding.toString(16).padStart(4, "0"); // e.g., "0d70"
  
        // Convert to 32-bit little-endian hex: "0000" + iiii → swap bytes
        const littleEndianHex = `${hexEncoding.slice(2, 4)}${hexEncoding.slice(0, 2)}0000`;
        
        // Ensure 8 digits
        result.push(littleEndianHex.toUpperCase());
    }
  
    return result;
}

function convertArm64MachineCodeToUdf(hexCodes) {
    const result = [];
  
    for (const hex of hexCodes) {
        // Ensure the input is a valid 8-digit hex string
        const hexClean = hex.trim().toLowerCase();
        if (!/^[0-9a-f]{8}$/.test(hexClean)) {
            throw new Error(`Invalid hex code: ${hex}. Expected 8-digit hex (e.g., "700D0000")`);
        }
  
        // Parse the 32-bit hex value
        const hexValue = parseInt(hexClean, 16);
  
        // Extract the immediate (reverse little-endian)
        // Little-endian hex: "700D0000" → bytes [70, 0D, 00, 00] → big-endian "00000D70"
        const byte0 = (hexValue >> 24) & 0xFF; // Most significant byte (e.g., 70)
        const byte1 = (hexValue >> 16) & 0xFF; // (e.g., 0D)
        const byte2 = (hexValue >> 8) & 0xFF;  // (e.g., 00)
        const byte3 = hexValue & 0xFF;       // Least significant byte (e.g., 00)
  
        // ARM64 udf encoding: "0000iiii" → immediate is in the lower 16 bits
        // Reconstruct the immediate from little-endian: [byte1, byte0] = [0D, 70] → 0D70
        const immediate = (byte1 << 8) | byte0;
  
        // Verify the upper 16 bits are 0 (consistent with udf encoding)
        if (byte2 !== 0 || byte3 !== 0) {
            throw new Error(`Hex code ${hex} does not match udf pattern (upper 16 bits must be 0)`);
        }
  
        // Convert immediate to hex string and format as "udf #0xiiii"
        const immediateHex = immediate.toString(16).padStart(4, "0");
        result.push(`udf #0x${immediateHex}`);
    }
  
    return result;
}

const instructions = ["udf #0x3c0"];
const machineCode = convertUdfToArm64MachineCode(instructions);
console.log(machineCode); // ["700D0000", "A0050000"]
const backToAssembly = convertArm64MachineCodeToUdf(machineCode);
console.log(backToAssembly); // ["udf #0xd70", "udf #0x5a0"]
