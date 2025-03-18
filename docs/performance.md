# Performance Optimization Guide

This document describes various performance optimizations and resource management strategies implemented in Mirrobot.

## OCR Performance

### Image Preprocessing

Mirrobot applies several preprocessing steps to improve OCR accuracy and performance:

1. **Grayscale Conversion** - Converts colored images to grayscale
2. **Noise Reduction** - Uses median filtering to remove noise
3. **Contrast Enhancement** - Improves text/background differentiation
4. **Binarization** - Converts to pure black and white for clearer text

### Caching

The OCR system implements caching to avoid reprocessing identical images:

- Images are hashed using MD5 for cache lookup
- Cache entries include timestamp for expiration management
- Cache size is limited to prevent excessive memory usage

### Image Size Management

Large images are automatically downscaled before processing:

- Maximum dimension is capped at 3000 pixels
- Aspect ratio is maintained during resizing
- Downscaling uses high-quality LANCZOS algorithm

## Resource Management

### Memory Monitoring

The `ResourceMonitor` provides active monitoring of:

- Memory usage
- Disk space
- Log file size

When thresholds are exceeded, warnings are logged to help prevent performance degradation.

### Log Management

The `LogManager` handles log rotation and cleanup:

- Old logs are automatically archived using gzip compression
- Logs older than the configured retention period are removed
- Statistics on log size are available through the manager

## Best Practices

1. **Regular Restarts** - For long-running instances, consider scheduling regular restarts
2. **Monitor Queue Stats** - Use `!status` to check OCR queue metrics
3. **Optimize Tesseract Parameters** - Adjust PSM modes based on your typical images
4. **Language Data Selection** - Use the appropriate Tesseract data files (fast/best) for your needs

## Configuration Recommendations

### For Low-Resource Environments

```json
{
  "ocr_worker_count": 2,
  "ocr_max_queue_size": 20
}
```

### For High-Performance Environments

```json
{
  "ocr_worker_count": 8,
  "ocr_max_queue_size": 100
}
```

## System Requirements

Minimum recommended specifications:
- 2GB RAM
- Dual-core CPU
- 10GB free disk space

Optimal specifications:
- 4GB+ RAM
- Quad-core CPU
- 20GB+ free disk space
