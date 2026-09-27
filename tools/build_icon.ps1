param(
    [string]$Source = (Join-Path $PSScriptRoot '..\assets\zero_hour_archipelago.png'),
    [string]$Destination = (Join-Path $PSScriptRoot '..\assets\zero_hour_archipelago.ico')
)

$ErrorActionPreference = 'Stop'

# Trim empty margins before fitting the artwork to each icon size. Preserve its
# proportions and transparency, including at common scaled taskbar sizes.
Add-Type -AssemblyName System.Drawing
if (-not ('IconAlphaBounds' -as [type])) {
    Add-Type -ReferencedAssemblies @([System.Drawing.Bitmap].Assembly.Location, [System.Drawing.Rectangle].Assembly.Location) -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
public static class IconAlphaBounds {
    public static Rectangle Find(Bitmap image) {
        var data = image.LockBits(new Rectangle(0, 0, image.Width, image.Height),
            ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        int left=image.Width, top=image.Height, right=-1, bottom=-1;
        try {
            byte[] row = new byte[image.Width * 4];
            for (int y=0; y<image.Height; y++) {
                Marshal.Copy(IntPtr.Add(data.Scan0, y * data.Stride), row, 0, row.Length);
                for (int x=0; x<image.Width; x++) {
                    // Ignore near-invisible export residue around the emblem.
                    if (row[x*4+3] < 8) continue;
                    left=Math.Min(left,x); right=Math.Max(right,x);
                    top=Math.Min(top,y); bottom=Math.Max(bottom,y);
                }
            }
        } finally { image.UnlockBits(data); }
        if (right < left) throw new ArgumentException("The icon image is fully transparent.");
        // Two source pixels retain the outer antialiased edge when resampling.
        left=Math.Max(0,left-2); top=Math.Max(0,top-2);
        right=Math.Min(image.Width-1,right+2); bottom=Math.Min(image.Height-1,bottom+2);
        return Rectangle.FromLTRB(left,top,right+1,bottom+1);
    }
}
'@
}
$sourceImage = [System.Drawing.Bitmap]::FromFile([IO.Path]::GetFullPath($Source))
try {
    $sourceBounds = [IconAlphaBounds]::Find($sourceImage)
    Write-Output "Artwork bounds: $sourceBounds"
    $frames = foreach ($size in @(16, 20, 24, 32, 40, 48, 64, 96, 128, 192, 256)) {
        $bitmap = [System.Drawing.Bitmap]::new($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $stream = [IO.MemoryStream]::new()
        try {
            $graphics.Clear([System.Drawing.Color]::Transparent)
            $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $scale = [Math]::Min($size / $sourceBounds.Width, $size / $sourceBounds.Height)
            $width = [int][Math]::Round($sourceBounds.Width * $scale)
            $height = [int][Math]::Round($sourceBounds.Height * $scale)
            $x = [int][Math]::Floor(($size - $width) / 2)
            $y = [int][Math]::Floor(($size - $height) / 2)
            $graphics.DrawImage($sourceImage, [System.Drawing.Rectangle]::new($x, $y, $width, $height),
                $sourceBounds, [System.Drawing.GraphicsUnit]::Pixel)
            $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
            [pscustomobject]@{ Size = $size; Bytes = $stream.ToArray() }
        } finally {
            $stream.Dispose()
            $graphics.Dispose()
            $bitmap.Dispose()
        }
    }
} finally { $sourceImage.Dispose() }

$outputStream = [IO.File]::Create([IO.Path]::GetFullPath($Destination))
$writer = [IO.BinaryWriter]::new($outputStream)
try {
    $writer.Write([uint16]0)
    $writer.Write([uint16]1)
    $writer.Write([uint16]$frames.Count)
    $offset = 6 + 16 * $frames.Count
    foreach ($frame in $frames) {
        $dimension = if ($frame.Size -eq 256) { 0 } else { $frame.Size }
        $writer.Write([byte]$dimension)
        $writer.Write([byte]$dimension)
        $writer.Write([uint16]0)
        $writer.Write([uint16]1)
        $writer.Write([uint16]32)
        $writer.Write([uint32]$frame.Bytes.Length)
        $writer.Write([uint32]$offset)
        $offset += $frame.Bytes.Length
    }
    foreach ($frame in $frames) { $writer.Write([byte[]]$frame.Bytes) }
} finally { $writer.Dispose() }
Write-Output "Built transparent icon: $Destination"
