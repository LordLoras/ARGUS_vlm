import type { GraphData, GraphResponse, ExpandResponse, GraphNode, GraphLink } from "./types";

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/* ─── Initial graph (~20 nodes) ─────────────────────────────── */

const INITIAL_NODES: GraphNode[] = [
  // Companies
  { id: "stellantis", label: "Stellantis N.V.", type: "company", description: "Multinational automotive manufacturing corporation formed by the 50-50 merger of FCA and PSA Group.", industries: ["Automotive"], headquarters: "Amsterdam, Netherlands", founded: "2021", website: "stellantis.com" },
  { id: "fca", label: "Fiat Chrysler Automobiles", type: "company", description: "Italo-American multinational automotive manufacturer, predecessor of Stellantis.", industries: ["Automotive"], headquarters: "London, UK", founded: "2014" },
  { id: "psa", label: "PSA Group", type: "company", description: "French multinational automotive manufacturer, predecessor of Stellantis.", industries: ["Automotive"], headquarters: "Rueil-Malmaison, France", founded: "1976" },
  { id: "gm", label: "General Motors", type: "company", description: "American multinational automotive manufacturing company.", industries: ["Automotive"], headquarters: "Detroit, Michigan, USA", founded: "1908", website: "gm.com" },
  { id: "ford", label: "Ford Motor Company", type: "company", description: "American multinational automobile manufacturer.", industries: ["Automotive"], headquarters: "Dearborn, Michigan, USA", founded: "1903", website: "ford.com" },
  { id: "toyota", label: "Toyota Motor Corporation", type: "company", description: "Japanese multinational automotive manufacturer.", industries: ["Automotive"], headquarters: "Toyota City, Japan", founded: "1937", website: "global.toyota" },
  // Brands
  { id: "ram", label: "RAM Trucks", type: "brand", description: "American brand of light to mid-weight trucks and vans, a division of Stellantis.", industries: ["Automotive", "Trucks"], parentCompany: "Stellantis" },
  { id: "jeep", label: "Jeep", type: "brand", description: "American automobile brand known for SUVs and off-road vehicles, a division of Stellantis.", industries: ["Automotive", "SUVs"], parentCompany: "Stellantis" },
  { id: "dodge", label: "Dodge", type: "brand", description: "American automobile brand known for performance cars and SUVs, a division of Stellantis.", industries: ["Automotive", "Performance"], parentCompany: "Stellantis" },
  { id: "chrysler", label: "Chrysler", type: "brand", description: "American luxury automobile brand, a division of Stellantis.", industries: ["Automotive", "Luxury"], parentCompany: "Stellantis" },
  { id: "fiat", label: "Fiat", type: "brand", description: "Italian automobile manufacturer, a subsidiary of Stellantis.", industries: ["Automotive", "Compact"], parentCompany: "Stellantis", headquarters: "Turin, Italy", founded: "1899" },
  { id: "peugeot", label: "Peugeot", type: "brand", description: "French automotive brand, a subsidiary of Stellantis.", industries: ["Automotive"], parentCompany: "Stellantis", headquarters: "Sochaux, France", founded: "1810" },
  { id: "chevrolet", label: "Chevrolet", type: "brand", description: "American automobile division of General Motors.", industries: ["Automotive"], parentCompany: "General Motors", founded: "1911" },
  { id: "gmc", label: "GMC", type: "brand", description: "American vehicle division of General Motors focused on trucks and utility vehicles.", industries: ["Automotive", "Trucks"], parentCompany: "General Motors" },
  // Categories
  { id: "automotive", label: "Automotive", type: "category", description: "The automotive industry encompasses design, development, and manufacturing of motor vehicles." },
  { id: "pickup-truck", label: "Pickup Truck", type: "category", description: "Light-duty truck with an open cargo area." },
  { id: "suv", label: "SUV", type: "category", description: "Sport Utility Vehicle — a rugged automotive combining passenger and cargo space." },
  { id: "luxury", label: "Luxury Vehicle", type: "category", description: "Premium vehicles with enhanced comfort, quality, and features." },
  // Products
  { id: "ram-1500", label: "RAM 1500", type: "product", description: "Full-size pickup truck, flagship of the RAM brand.", categories: ["Pickup Truck"] },
  { id: "ram-2500", label: "RAM 2500", type: "product", description: "Heavy-duty pickup truck in the RAM lineup.", categories: ["Pickup Truck"] },
  { id: "jeep-grand-cherokee", label: "Jeep Grand Cherokee", type: "product", description: "Mid-size luxury SUV produced by Jeep.", categories: ["SUV", "Luxury"] },
  { id: "dodge-durango", label: "Dodge Durango", type: "product", description: "Mid-size SUV produced by Dodge.", categories: ["SUV"] },
];

const INITIAL_LINKS: GraphLink[] = [
  // Company → Brand
  { source: "stellantis", target: "ram", label: "owns", strength: 1 },
  { source: "stellantis", target: "jeep", label: "owns", strength: 1 },
  { source: "stellantis", target: "dodge", label: "owns", strength: 1 },
  { source: "stellantis", target: "chrysler", label: "owns", strength: 1 },
  { source: "stellantis", target: "fiat", label: "owns", strength: 1 },
  { source: "stellantis", target: "peugeot", label: "owns", strength: 1 },
  { source: "fca", target: "stellantis", label: "merged_into", strength: 0.7 },
  { source: "psa", target: "stellantis", label: "merged_into", strength: 0.7 },
  { source: "fca", target: "ram", label: "owned", strength: 0.6 },
  { source: "fca", target: "jeep", label: "owned", strength: 0.6 },
  { source: "psa", target: "peugeot", label: "owned", strength: 0.6 },
  { source: "gm", target: "chevrolet", label: "owns", strength: 1 },
  { source: "gm", target: "gmc", label: "owns", strength: 1 },
  { source: "ford", target: "automotive", label: "operates_in", strength: 0.5 },
  { source: "toyota", target: "automotive", label: "operates_in", strength: 0.5 },
  // Brand → Category
  { source: "ram", target: "pickup-truck", label: "category", strength: 0.8 },
  { source: "jeep", target: "suv", label: "category", strength: 0.8 },
  { source: "dodge", target: "suv", label: "category", strength: 0.6 },
  { source: "chrysler", target: "luxury", label: "category", strength: 0.7 },
  // Brand → Product
  { source: "ram", target: "ram-1500", label: "produces", strength: 0.9 },
  { source: "ram", target: "ram-2500", label: "produces", strength: 0.9 },
  { source: "jeep", target: "jeep-grand-cherokee", label: "produces", strength: 0.9 },
  { source: "dodge", target: "dodge-durango", label: "produces", strength: 0.9 },
  // Category → Product
  { source: "pickup-truck", target: "ram-1500", label: "includes", strength: 0.7 },
  { source: "pickup-truck", target: "ram-2500", label: "includes", strength: 0.7 },
  { source: "suv", target: "jeep-grand-cherokee", label: "includes", strength: 0.7 },
  { source: "suv", target: "dodge-durango", label: "includes", strength: 0.7 },
  // Company → Category
  { source: "stellantis", target: "automotive", label: "operates_in", strength: 0.5 },
  { source: "gm", target: "pickup-truck", label: "operates_in", strength: 0.4 },
  { source: "gm", target: "suv", label: "operates_in", strength: 0.4 },
  { source: "stellantis", target: "pickup-truck", label: "operates_in", strength: 0.4 },
  { source: "stellantis", target: "suv", label: "operates_in", strength: 0.4 },
];

/* ─── Expansion data ────────────────────────────────────────── */

const EXPANSIONS: Record<string, GraphData> = {
  "ram": {
    nodes: [
      { id: "ram-trx", label: "RAM 1500 TRX", type: "product", description: "High-performance off-road pickup truck.", categories: ["Pickup Truck", "Performance"] },
      { id: "ram-promaster", label: "RAM ProMaster", type: "product", description: "Full-size van used for commercial applications.", categories: ["Commercial Vehicle"] },
      { id: "ram-classic", label: "RAM 1500 Classic", type: "product", description: "Previous-generation RAM 1500 sold alongside the newer model.", categories: ["Pickup Truck"] },
      { id: "commercial-vehicle", label: "Commercial Vehicle", type: "category", description: "Vehicles designed for commercial and fleet use." },
    ],
    links: [
      { source: "ram", target: "ram-trx", label: "produces", strength: 0.9 },
      { source: "ram", target: "ram-promaster", label: "produces", strength: 0.9 },
      { source: "ram", target: "ram-classic", label: "produces", strength: 0.9 },
      { source: "pickup-truck", target: "ram-trx", label: "includes", strength: 0.7 },
      { source: "ram", target: "commercial-vehicle", label: "category", strength: 0.5 },
      { source: "commercial-vehicle", target: "ram-promaster", label: "includes", strength: 0.7 },
    ],
  },
  "stellantis": {
    nodes: [
      { id: "maserati", label: "Maserati", type: "brand", description: "Italian luxury vehicle manufacturer, a subsidiary of Stellantis.", industries: ["Automotive", "Luxury"], parentCompany: "Stellantis", headquarters: "Modena, Italy", founded: "1914" },
      { id: "alfa-romeo", label: "Alfa Romeo", type: "brand", description: "Italian premium automobile manufacturer, a subsidiary of Stellantis.", industries: ["Automotive", "Luxury"], parentCompany: "Stellantis", headquarters: "Turin, Italy", founded: "1910" },
      { id: "citroen", label: "Citroen", type: "brand", description: "French automobile manufacturer, a subsidiary of Stellantis.", industries: ["Automotive"], parentCompany: "Stellantis", headquarters: "Saint-Ouen-sur-Seine, France", founded: "1919" },
      { id: "ds", label: "DS Automobiles", type: "brand", description: "French luxury vehicle manufacturer, a subsidiary of Stellantis.", industries: ["Automotive", "Luxury"], parentCompany: "Stellantis" },
      { id: "opel", label: "Opel", type: "brand", description: "German automobile manufacturer, a subsidiary of Stellantis.", industries: ["Automotive"], parentCompany: "Stellantis", headquarters: "Russelsheim, Germany", founded: "1862" },
      { id: "leapmotor", label: "Leapmotor", type: "subsidiary", description: "Chinese EV manufacturer, Stellantis holds a significant stake.", industries: ["Automotive", "Electric Vehicles"], parentCompany: "Stellantis" },
    ],
    links: [
      { source: "stellantis", target: "maserati", label: "owns", strength: 1 },
      { source: "stellantis", target: "alfa-romeo", label: "owns", strength: 1 },
      { source: "stellantis", target: "citroen", label: "owns", strength: 1 },
      { source: "stellantis", target: "ds", label: "owns", strength: 1 },
      { source: "stellantis", target: "opel", label: "owns", strength: 1 },
      { source: "stellantis", target: "leapmotor", label: "partnership", strength: 0.6 },
      { source: "maserati", target: "luxury", label: "category", strength: 0.8 },
      { source: "alfa-romeo", target: "luxury", label: "category", strength: 0.7 },
      { source: "ds", target: "luxury", label: "category", strength: 0.7 },
      { source: "opel", target: "automotive", label: "operates_in", strength: 0.5 },
      { source: "citroen", target: "automotive", label: "operates_in", strength: 0.5 },
    ],
  },
  "suv": {
    nodes: [
      { id: "ford-explorer", label: "Ford Explorer", type: "product", description: "Mid-size SUV produced by Ford.", categories: ["SUV"], parentCompany: "Ford" },
      { id: "toyota-rav4", label: "Toyota RAV4", type: "product", description: "Compact crossover SUV produced by Toyota.", categories: ["SUV"], parentCompany: "Toyota" },
      { id: "honda-cr-v", label: "Honda CR-V", type: "product", description: "Compact crossover SUV produced by Honda.", categories: ["SUV"] },
      { id: "chevy-tahoe", label: "Chevrolet Tahoe", type: "product", description: "Full-size SUV produced by Chevrolet.", categories: ["SUV"], parentCompany: "General Motors" },
      { id: "jeep-wrangler", label: "Jeep Wrangler", type: "product", description: "Compact/mid-size off-road SUV produced by Jeep.", categories: ["SUV", "Off-road"] },
      { id: "ford", label: "Ford Motor Company", type: "company", description: "American multinational automobile manufacturer.", industries: ["Automotive"], headquarters: "Dearborn, Michigan, USA", founded: "1903" },
      { id: "honda", label: "Honda Motor Co.", type: "company", description: "Japanese multinational automotive manufacturer.", industries: ["Automotive"], headquarters: "Tokyo, Japan", founded: "1948" },
    ],
    links: [
      { source: "ford", target: "ford-explorer", label: "produces", strength: 0.9 },
      { source: "toyota", target: "toyota-rav4", label: "produces", strength: 0.9 },
      { source: "honda", target: "honda-cr-v", label: "produces", strength: 0.9 },
      { source: "chevrolet", target: "chevy-tahoe", label: "produces", strength: 0.9 },
      { source: "jeep", target: "jeep-wrangler", label: "produces", strength: 0.9 },
      { source: "suv", target: "ford-explorer", label: "includes", strength: 0.7 },
      { source: "suv", target: "toyota-rav4", label: "includes", strength: 0.7 },
      { source: "suv", target: "honda-cr-v", label: "includes", strength: 0.7 },
      { source: "suv", target: "chevy-tahoe", label: "includes", strength: 0.7 },
      { source: "suv", target: "jeep-wrangler", label: "includes", strength: 0.7 },
      { source: "ford", target: "automotive", label: "operates_in", strength: 0.5 },
      { source: "honda", target: "automotive", label: "operates_in", strength: 0.5 },
    ],
  },
  "pickup-truck": {
    nodes: [
      { id: "f150", label: "Ford F-150", type: "product", description: "Full-size pickup truck, best-selling vehicle in the US.", categories: ["Pickup Truck"], parentCompany: "Ford" },
      { id: "silverado", label: "Chevrolet Silverado", type: "product", description: "Full-size pickup truck produced by Chevrolet.", categories: ["Pickup Truck"], parentCompany: "General Motors" },
      { id: "tacoma", label: "Toyota Tacoma", type: "product", description: "Mid-size pickup truck produced by Toyota.", categories: ["Pickup Truck"], parentCompany: "Toyota" },
      { id: "gmc-sierra", label: "GMC Sierra", type: "product", description: "Full-size pickup truck produced by GMC.", categories: ["Pickup Truck"], parentCompany: "General Motors" },
      { id: "cybertruck", label: "Tesla Cybertruck", type: "product", description: "Battery electric pickup truck by Tesla.", categories: ["Pickup Truck", "Electric"] },
      { id: "tesla", label: "Tesla, Inc.", type: "company", description: "American multinational automotive and clean energy company.", industries: ["Automotive", "Electric Vehicles"], headquarters: "Austin, Texas, USA", founded: "2003" },
    ],
    links: [
      { source: "ford", target: "f150", label: "produces", strength: 0.9 },
      { source: "chevrolet", target: "silverado", label: "produces", strength: 0.9 },
      { source: "toyota", target: "tacoma", label: "produces", strength: 0.9 },
      { source: "gmc", target: "gmc-sierra", label: "produces", strength: 0.9 },
      { source: "tesla", target: "cybertruck", label: "produces", strength: 0.9 },
      { source: "pickup-truck", target: "f150", label: "includes", strength: 0.7 },
      { source: "pickup-truck", target: "silverado", label: "includes", strength: 0.7 },
      { source: "pickup-truck", target: "tacoma", label: "includes", strength: 0.7 },
      { source: "pickup-truck", target: "gmc-sierra", label: "includes", strength: 0.7 },
      { source: "pickup-truck", target: "cybertruck", label: "includes", strength: 0.7 },
      { source: "tesla", target: "automotive", label: "operates_in", strength: 0.5 },
    ],
  },
  "jeep": {
    nodes: [
      { id: "jeep-compass", label: "Jeep Compass", type: "product", description: "Compact crossover SUV produced by Jeep.", categories: ["SUV", "Compact"] },
      { id: "jeep-gladiator", label: "Jeep Gladiator", type: "product", description: "Mid-size pickup truck produced by Jeep.", categories: ["Pickup Truck"] },
      { id: "jeep-cherokee", label: "Jeep Cherokee", type: "product", description: "Compact SUV formerly produced by Jeep.", categories: ["SUV"] },
      { id: "off-road", label: "Off-Road Vehicle", type: "category", description: "Vehicles designed for off-highway and rugged terrain use." },
    ],
    links: [
      { source: "jeep", target: "jeep-compass", label: "produces", strength: 0.9 },
      { source: "jeep", target: "jeep-gladiator", label: "produces", strength: 0.9 },
      { source: "jeep", target: "jeep-cherokee", label: "produces", strength: 0.9 },
      { source: "jeep", target: "off-road", label: "category", strength: 0.8 },
      { source: "suv", target: "jeep-compass", label: "includes", strength: 0.7 },
      { source: "pickup-truck", target: "jeep-gladiator", label: "includes", strength: 0.7 },
      { source: "off-road", target: "jeep-wrangler", label: "includes", strength: 0.7 },
    ],
  },
  "fiat": {
    nodes: [
      { id: "fiat-500", label: "Fiat 500", type: "product", description: "Compact city car, icon of Italian automotive design.", categories: ["Compact", "City Car"] },
      { id: "fiat-panda", label: "Fiat Panda", type: "product", description: "Compact city car produced by Fiat.", categories: ["Compact", "City Car"] },
      { id: "fiat-500e", label: "Fiat 500e", type: "product", description: "All-electric version of the Fiat 500.", categories: ["Compact", "Electric"] },
      { id: "abarth", label: "Abarth", type: "subsidiary", description: "Italian performance car brand, a subsidiary of Stellantis.", industries: ["Automotive", "Performance"], parentCompany: "Stellantis" },
      { id: "city-car", label: "City Car", type: "category", description: "Compact automobiles designed for urban use." },
    ],
    links: [
      { source: "fiat", target: "fiat-500", label: "produces", strength: 0.9 },
      { source: "fiat", target: "fiat-panda", label: "produces", strength: 0.9 },
      { source: "fiat", target: "fiat-500e", label: "produces", strength: 0.9 },
      { source: "stellantis", target: "abarth", label: "owns", strength: 1 },
      { source: "abarth", target: "fiat", label: "performance_line", strength: 0.6 },
      { source: "fiat", target: "city-car", label: "category", strength: 0.7 },
      { source: "city-car", target: "fiat-500", label: "includes", strength: 0.7 },
      { source: "city-car", target: "fiat-panda", label: "includes", strength: 0.7 },
    ],
  },
  "maserati": {
    nodes: [
      { id: "maserati-mc20", label: "Maserati MC20", type: "product", description: "Mid-engine sports car by Maserati.", categories: ["Sports Car", "Luxury"] },
      { id: "maserati-levant", label: "Maserati Levante", type: "product", description: "Luxury crossover SUV by Maserati.", categories: ["SUV", "Luxury"] },
      { id: "sports-car", label: "Sports Car", type: "category", description: "Performance-oriented automobiles designed for speed and handling." },
    ],
    links: [
      { source: "maserati", target: "maserati-mc20", label: "produces", strength: 0.9 },
      { source: "maserati", target: "maserati-levant", label: "produces", strength: 0.9 },
      { source: "maserati", target: "sports-car", label: "category", strength: 0.8 },
      { source: "sports-car", target: "maserati-mc20", label: "includes", strength: 0.7 },
      { source: "suv", target: "maserati-levant", label: "includes", strength: 0.7 },
      { source: "luxury", target: "maserati-mc20", label: "includes", strength: 0.7 },
    ],
  },
  "alfa-romeo": {
    nodes: [
      { id: "giulia", label: "Alfa Romeo Giulia", type: "product", description: "Compact executive sedan by Alfa Romeo.", categories: ["Sedan", "Luxury"] },
      { id: "stelvio", label: "Alfa Romeo Stelvio", type: "product", description: "Compact luxury SUV by Alfa Romeo.", categories: ["SUV", "Luxury"] },
      { id: "sedan", label: "Sedan", type: "category", description: "Passenger car with a three-box configuration." },
    ],
    links: [
      { source: "alfa-romeo", target: "giulia", label: "produces", strength: 0.9 },
      { source: "alfa-romeo", target: "stelvio", label: "produces", strength: 0.9 },
      { source: "alfa-romeo", target: "sedan", label: "category", strength: 0.7 },
      { source: "sedan", target: "giulia", label: "includes", strength: 0.7 },
      { source: "suv", target: "stelvio", label: "includes", strength: 0.7 },
    ],
  },
  "chevrolet": {
    nodes: [
      { id: "corvette", label: "Chevrolet Corvette", type: "product", description: "Sports car by Chevrolet, an American icon.", categories: ["Sports Car"] },
      { id: "camaro", label: "Chevrolet Camaro", type: "product", description: "Muscle car/pony car by Chevrolet.", categories: ["Muscle Car"] },
      { id: "bolt", label: "Chevrolet Bolt EV", type: "product", description: "Compact electric hatchback by Chevrolet.", categories: ["Electric", "Compact"] },
    ],
    links: [
      { source: "chevrolet", target: "corvette", label: "produces", strength: 0.9 },
      { source: "chevrolet", target: "camaro", label: "produces", strength: 0.9 },
      { source: "chevrolet", target: "bolt", label: "produces", strength: 0.9 },
    ],
  },
  "ford": {
    nodes: [
      { id: "mustang", label: "Ford Mustang", type: "product", description: "American pony car/muscle car, in production since 1964.", categories: ["Muscle Car"] },
      { id: "bronco", label: "Ford Bronco", type: "product", description: "Off-road SUV by Ford.", categories: ["SUV", "Off-road"] },
      { id: "mustang-mach-e", label: "Ford Mustang Mach-E", type: "product", description: "Electric compact SUV by Ford.", categories: ["SUV", "Electric"] },
    ],
    links: [
      { source: "ford", target: "mustang", label: "produces", strength: 0.9 },
      { source: "ford", target: "bronco", label: "produces", strength: 0.9 },
      { source: "ford", target: "mustang-mach-e", label: "produces", strength: 0.9 },
      { source: "suv", target: "bronco", label: "includes", strength: 0.7 },
      { source: "suv", target: "mustang-mach-e", label: "includes", strength: 0.7 },
    ],
  },
  "gm": {
    nodes: [
      { id: "buick", label: "Buick", type: "brand", description: "American automobile brand, a division of General Motors.", industries: ["Automotive", "Luxury"], parentCompany: "General Motors" },
      { id: "cadillac", label: "Cadillac", type: "brand", description: "American luxury automobile brand, a division of General Motors.", industries: ["Automotive", "Luxury"], parentCompany: "General Motors", headquarters: "Detroit, Michigan, USA", founded: "1902" },
    ],
    links: [
      { source: "gm", target: "buick", label: "owns", strength: 1 },
      { source: "gm", target: "cadillac", label: "owns", strength: 1 },
      { source: "cadillac", target: "luxury", label: "category", strength: 0.8 },
      { source: "buick", target: "luxury", label: "category", strength: 0.7 },
    ],
  },
  "toyota": {
    nodes: [
      { id: "lexus", label: "Lexus", type: "brand", description: "Japanese luxury vehicle division of Toyota.", industries: ["Automotive", "Luxury"], parentCompany: "Toyota", headquarters: "Nagoya, Japan", founded: "1989" },
      { id: "camry", label: "Toyota Camry", type: "product", description: "Mid-size sedan, one of the best-selling cars globally.", categories: ["Sedan"] },
      { id: "land-cruiser", label: "Toyota Land Cruiser", type: "product", description: "Legendary off-road SUV by Toyota.", categories: ["SUV", "Off-road"] },
    ],
    links: [
      { source: "toyota", target: "lexus", label: "owns", strength: 1 },
      { source: "toyota", target: "camry", label: "produces", strength: 0.9 },
      { source: "toyota", target: "land-cruiser", label: "produces", strength: 0.9 },
      { source: "lexus", target: "luxury", label: "category", strength: 0.8 },
    ],
  },
  "tesla": {
    nodes: [
      { id: "model-y", label: "Tesla Model Y", type: "product", description: "Compact crossover SUV by Tesla.", categories: ["SUV", "Electric"] },
      { id: "model-3", label: "Tesla Model 3", type: "product", description: "Compact executive sedan by Tesla.", categories: ["Sedan", "Electric"] },
      { id: "electric-vehicle", label: "Electric Vehicle", type: "category", description: "Vehicles powered by electric motors and battery packs." },
    ],
    links: [
      { source: "tesla", target: "model-y", label: "produces", strength: 0.9 },
      { source: "tesla", target: "model-3", label: "produces", strength: 0.9 },
      { source: "tesla", target: "electric-vehicle", label: "category", strength: 0.8 },
      { source: "electric-vehicle", target: "model-y", label: "includes", strength: 0.7 },
      { source: "electric-vehicle", target: "model-3", label: "includes", strength: 0.7 },
      { source: "electric-vehicle", target: "cybertruck", label: "includes", strength: 0.7 },
    ],
  },
  "peugeot": {
    nodes: [
      { id: "peugeot-208", label: "Peugeot 208", type: "product", description: "Compact city car by Peugeot.", categories: ["Compact", "City Car"] },
      { id: "peugeot-3008", label: "Peugeot 3008", type: "product", description: "Compact crossover SUV by Peugeot.", categories: ["SUV"] },
    ],
    links: [
      { source: "peugeot", target: "peugeot-208", label: "produces", strength: 0.9 },
      { source: "peugeot", target: "peugeot-3008", label: "produces", strength: 0.9 },
      { source: "suv", target: "peugeot-3008", label: "includes", strength: 0.7 },
    ],
  },
  "dodge": {
    nodes: [
      { id: "dodge-charger", label: "Dodge Charger", type: "product", description: "Full-size sedan/muscle car by Dodge.", categories: ["Sedan", "Muscle Car"] },
      { id: "dodge-challenger", label: "Dodge Challenger", type: "product", description: "Pony car/muscle car by Dodge.", categories: ["Muscle Car"] },
      { id: "muscle-car", label: "Muscle Car", type: "category", description: "American high-performance automobiles with powerful engines." },
    ],
    links: [
      { source: "dodge", target: "dodge-charger", label: "produces", strength: 0.9 },
      { source: "dodge", target: "dodge-challenger", label: "produces", strength: 0.9 },
      { source: "dodge", target: "muscle-car", label: "category", strength: 0.8 },
      { source: "muscle-car", target: "dodge-charger", label: "includes", strength: 0.7 },
      { source: "muscle-car", target: "dodge-challenger", label: "includes", strength: 0.7 },
    ],
  },
  "chrysler": {
    nodes: [
      { id: "chrysler-300", label: "Chrysler 300", type: "product", description: "Full-size luxury sedan by Chrysler.", categories: ["Sedan", "Luxury"] },
      { id: "chrysler-pacifica", label: "Chrysler Pacifica", type: "product", description: "Minivan by Chrysler, also available as a plug-in hybrid.", categories: ["Minivan"] },
      { id: "minivan", label: "Minivan", type: "category", description: "Multi-purpose vehicle designed for passenger and cargo capacity." },
    ],
    links: [
      { source: "chrysler", target: "chrysler-300", label: "produces", strength: 0.9 },
      { source: "chrysler", target: "chrysler-pacifica", label: "produces", strength: 0.9 },
      { source: "chrysler", target: "luxury", label: "category", strength: 0.7 },
      { source: "chrysler", target: "minivan", label: "category", strength: 0.7 },
      { source: "minivan", target: "chrysler-pacifica", label: "includes", strength: 0.7 },
      { source: "luxury", target: "chrysler-300", label: "includes", strength: 0.7 },
    ],
  },
  "gmc": {
    nodes: [
      { id: "gmc-sierra", label: "GMC Sierra", type: "product", description: "Full-size pickup truck by GMC.", categories: ["Pickup Truck"] },
      { id: "gmc-terrain", label: "GMC Terrain", type: "product", description: "Compact crossover SUV by GMC.", categories: ["SUV", "Compact"] },
      { id: "gmc-yukon", label: "GMC Yukon", type: "product", description: "Full-size SUV by GMC.", categories: ["SUV"] },
    ],
    links: [
      { source: "gmc", target: "gmc-sierra", label: "produces", strength: 0.9 },
      { source: "gmc", target: "gmc-terrain", label: "produces", strength: 0.9 },
      { source: "gmc", target: "gmc-yukon", label: "produces", strength: 0.9 },
      { source: "pickup-truck", target: "gmc-sierra", label: "includes", strength: 0.7 },
      { source: "suv", target: "gmc-terrain", label: "includes", strength: 0.7 },
      { source: "suv", target: "gmc-yukon", label: "includes", strength: 0.7 },
    ],
  },
  "ram-1500": {
    nodes: [
      { id: "ram-trx", label: "RAM 1500 TRX", type: "product", description: "High-performance off-road pickup truck.", categories: ["Pickup Truck", "Performance"] },
      { id: "ram-rebel", label: "RAM 1500 Rebel", type: "product", description: "Off-road oriented trim of the RAM 1500.", categories: ["Pickup Truck", "Off-road"] },
    ],
    links: [
      { source: "ram", target: "ram-trx", label: "produces", strength: 0.9 },
      { source: "ram", target: "ram-rebel", label: "produces", strength: 0.9 },
      { source: "pickup-truck", target: "ram-trx", label: "includes", strength: 0.7 },
      { source: "pickup-truck", target: "ram-rebel", label: "includes", strength: 0.7 },
    ],
  },
  "ram-2500": {
    nodes: [
      { id: "ram-power-wagon", label: "RAM Power Wagon", type: "product", description: "Heavy-duty off-road pickup truck by RAM.", categories: ["Pickup Truck", "Off-road"] },
    ],
    links: [
      { source: "ram", target: "ram-power-wagon", label: "produces", strength: 0.9 },
      { source: "pickup-truck", target: "ram-power-wagon", label: "includes", strength: 0.7 },
    ],
  },
  "jeep-grand-cherokee": {
    nodes: [
      { id: "jeep-wagoneer", label: "Jeep Grand Wagoneer", type: "product", description: "Full-size luxury SUV by Jeep.", categories: ["SUV", "Luxury"] },
    ],
    links: [
      { source: "jeep", target: "jeep-wagoneer", label: "produces", strength: 0.9 },
      { source: "luxury", target: "jeep-wagoneer", label: "includes", strength: 0.7 },
    ],
  },
  "dodge-durango": {
    nodes: [
      { id: "dodge-durango-srt", label: "Dodge Durango SRT", type: "product", description: "High-performance version of the Dodge Durango SUV.", categories: ["SUV", "Performance"] },
      { id: "performance", label: "Performance Vehicle", type: "category", description: "Vehicles designed for high-speed capability and driving dynamics." },
    ],
    links: [
      { source: "dodge", target: "dodge-durango-srt", label: "produces", strength: 0.9 },
      { source: "dodge", target: "performance", label: "category", strength: 0.7 },
      { source: "performance", target: "dodge-durango-srt", label: "includes", strength: 0.7 },
    ],
  },
  "luxury": {
    nodes: [
      { id: "bmw", label: "BMW Group", type: "company", description: "German multinational automotive manufacturer known for luxury and performance vehicles.", industries: ["Automotive", "Luxury"], headquarters: "Munich, Germany", founded: "1916" },
      { id: "mercedes", label: "Mercedes-Benz Group", type: "company", description: "German multinational automotive corporation known for premium vehicles.", industries: ["Automotive", "Luxury"], headquarters: "Stuttgart, Germany", founded: "1926" },
    ],
    links: [
      { source: "bmw", target: "luxury", label: "operates_in", strength: 0.8 },
      { source: "mercedes", target: "luxury", label: "operates_in", strength: 0.8 },
      { source: "bmw", target: "automotive", label: "operates_in", strength: 0.5 },
      { source: "mercedes", target: "automotive", label: "operates_in", strength: 0.5 },
    ],
  },
  "automotive": {
    nodes: [
      { id: "hyundai", label: "Hyundai Motor Company", type: "company", description: "South Korean multinational automotive manufacturer.", industries: ["Automotive"], headquarters: "Seoul, South Korea", founded: "1967" },
      { id: "vw-group", label: "Volkswagen Group", type: "company", description: "German multinational automotive manufacturing company, the largest automaker in Europe.", industries: ["Automotive", "Luxury"], headquarters: "Wolfsburg, Germany", founded: "1937" },
    ],
    links: [
      { source: "hyundai", target: "automotive", label: "operates_in", strength: 0.5 },
      { source: "vw-group", target: "automotive", label: "operates_in", strength: 0.5 },
    ],
  },
};

export async function getInitialGraph(): Promise<GraphResponse> {
  await delay(600);
  return {
    nodes: INITIAL_NODES,
    links: INITIAL_LINKS,
    meta: {
      total_nodes: INITIAL_NODES.length,
      total_links: INITIAL_LINKS.length,
      seed_node: "ram",
    },
  };
}

export async function expandNode(nodeId: string): Promise<ExpandResponse> {
  const expansion = EXPANSIONS[nodeId];
  if (!expansion) {
    return { new_nodes: [], new_links: [], expanded_from: nodeId };
  }
  const allKnownIds = new Set<string>();
  INITIAL_NODES.forEach((n) => allKnownIds.add(n.id));
  for (const key of Object.keys(EXPANSIONS)) {
    EXPANSIONS[key].nodes.forEach((n) => allKnownIds.add(n.id));
  }
  const newNodes = expansion.nodes.filter((n) => !allKnownIds.has(n.id));
  const newLinks = expansion.links.filter(
    (l) => {
      const s = typeof l.source === "string" ? l.source : (l.source as GraphNode).id;
      const t = typeof l.target === "string" ? l.target : (l.target as GraphNode).id;
      return !allKnownIds.has(s) || !allKnownIds.has(t);
    }
  );
  await delay(1200 + Math.random() * 800);
  return {
    new_nodes: newNodes,
    new_links: newLinks,
    expanded_from: nodeId,
  };
}
