<#
.SYNOPSIS
    Kişisel Offline AI Sistemi — Windows Güvenlik Duvarı Dış Bağlantı Engelleme Aracı
.DESCRIPTION
    İsteğe bağlı olarak Ollama yürütülebilir dosyalarının (ollama.exe ve ollama app.exe)
    dış ağa (İnternet) çıkışını Windows Güvenlik Duvarı üzerinden tamamen engeller.
    Not: Yeni model indirmek istediğinizde -Action Allow parametresiyle geçici olarak açabilirsiniz.
.PARAMETER Action
    Status : Mevcut güvenlik duvarı kurallarını kontrol eder (Yönetici izni gerekmez).
    Block  : Ollama için dış ağ çıkışlarını engeller (Yönetici izni gerekir).
    Allow  : Oluşturulan engelleme kurallarını kaldırır (Yönetici izni gerekir).
#>
param(
    [ValidateSet("Status", "Block", "Allow")]
    [string]$Action = "Status"
)

$RulePrefix = "OfflineAI_Block_Outbound"
$OllamaDir = "$env:LOCALAPPDATA\Programs\Ollama"
$Targets = @(
    @{ Name = "${RulePrefix}_CLI"; Path = "$OllamaDir\ollama.exe" },
    @{ Name = "${RulePrefix}_App"; Path = "$OllamaDir\ollama app.exe" }
)

if ($Action -eq "Status") {
    Write-Host "=== WINDOWS GÜVENLİK DUVARI KURAL DURUMU ===" -ForegroundColor Cyan
    foreach ($t in $Targets) {
        $rule = Get-NetFirewallRule -DisplayName $t.Name -ErrorAction SilentlyContinue
        if ($rule) {
            Write-Host "[AKTİF ENGEL] $($t.Name) -> Enabled: $($rule.Enabled), Action: $($rule.Action)" -ForegroundColor Green
        } else {
            Write-Host "[KURAL YOK]   $($t.Name) (Uygulama şu an केवळ localhost 127.0.0.1:11434 üzerinde kısıtlı)" -ForegroundColor Yellow
        }
    }
    exit 0
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "UYARI: Güvenlik duvarı kuralı eklemek/kaldırmak için PowerShell'i Yönetici Olarak çalıştırmalısınız." -ForegroundColor Red
    Write-Host "Örnek komut (Yönetici PowerShell içinde):" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Action $Action"
    exit 1
}

if ($Action -eq "Block") {
    foreach ($t in $Targets) {
        Remove-NetFirewallRule -DisplayName $t.Name -ErrorAction SilentlyContinue
        New-NetFirewallRule -DisplayName $t.Name `
            -Direction Outbound `
            -Program $t.Path `
            -Action Block `
            -Profile Any `
            -Description "Kişisel Offline AI: Ollama dış internet erişimini engeller." | Out-Null
        Write-Host "[ENGELLENDİ] Dış ağ çıkışı kapatıldı: $($t.Path)" -ForegroundColor Green
    }
} elseif ($Action -eq "Allow") {
    foreach ($t in $Targets) {
        Remove-NetFirewallRule -DisplayName $t.Name -ErrorAction SilentlyContinue
        Write-Host "[İZİN VERİLDİ] Engelleme kuralı kaldırıldı: $($t.Name)" -ForegroundColor Cyan
    }
}
