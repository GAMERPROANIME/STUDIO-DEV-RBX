--!strict
-- Shared combat configuration. Required by both server and client modules.
export type WeaponConfig = {
	Name: string,
	Damage: number,
	Range: number,
	Cooldown: number,
	Knockback: number,
}

local CombatConfig = {
	MaxHealth = 100,
	RespawnTime = 3,
	HitboxSize = Vector3.new(4, 4, 4),
	Weapons = {
		Sword = { Name = "Sword", Damage = 15, Range = 8, Cooldown = 0.6, Knockback = 12 },
		Hammer = { Name = "Hammer", Damage = 30, Range = 7, Cooldown = 1.4, Knockback = 30 },
		Dagger = { Name = "Dagger", Damage = 8, Range = 6, Cooldown = 0.3, Knockback = 4 },
	} :: { [string]: WeaponConfig },
}

return CombatConfig
