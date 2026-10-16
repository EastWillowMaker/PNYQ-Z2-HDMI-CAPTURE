/* Exact RGB source using direct DRM/KMS on a separate active Linux VT.
 * Build: scripts/build_kms_fixture.sh. Refuses operation without DRM master.
 * Use run_kms_vt.py to switch back to the desktop after bounded execution.
 */
#define _POSIX_C_SOURCE 200809L
#include <drm_fourcc.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

struct profile {
  const char *name;
  unsigned width, height;
  unsigned h_front, h_sync, h_back;
  unsigned v_front, v_sync, v_back;
  bool h_positive, v_positive;
  const unsigned *clocks_khz;
  size_t clock_count;
};
static const unsigned vga_clocks[] = {25175, 25200};
static const unsigned hd1080_clocks[] = {74250};
static const struct profile profiles[] = {
    {"vga", 640, 480, 16, 96, 48, 10, 2, 33, false, false,
     vga_clocks, sizeof vga_clocks / sizeof vga_clocks[0]},
    {"1080p30", 1920, 1080, 88, 44, 148, 4, 5, 36, true, true,
     hd1080_clocks, sizeof hd1080_clocks / sizeof hd1080_clocks[0]},
};
static int drm_fd = -1;
static volatile sig_atomic_t stop;
static void interrupted(int sig) {
  (void)sig;
  stop = 1;
}
static double now(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec + ts.tv_nsec / 1e9;
}
static uint32_t pixel(uint32_t id, unsigned x, unsigned y) {
  unsigned r = (x + 3 * y + (id & 255)) & 255,
           g = (5 * x + y + ((id >> 8) & 255)) & 255;
  unsigned b = (x ^ y ^ ((id >> 16) & 255)) & 255;
  if (x < 128) {
    unsigned bit = (id >> ((x % 64) / 2)) & 1;
    r = g = b = (x < 64 ? bit : 1 - bit) * 255;
  } else if (x <= 132) {
    r = (x == 128 || x == 132) ? 255 : 0;
    g = (x == 129 || x == 132) ? 255 : 0;
    b = (x == 130 || x == 132) ? 255 : 0;
  }
  if (x >= 160 && x < 416 && y >= 16 && y < 64) {
    r = (y < 32) ? x - 160 : 0;
    g = (y >= 32 && y < 48) ? x - 160 : 0;
    b = (y >= 48) ? x - 160 : 0;
  }
  return (r << 16) | (g << 8) | b;
}
static const struct profile *find_profile(const char *name) {
  for (size_t i = 0; i < sizeof profiles / sizeof profiles[0]; i++)
    if (!strcmp(name, profiles[i].name))
      return &profiles[i];
  return NULL;
}
static bool matches_profile(const drmModeModeInfo *mode,
                            const struct profile *profile) {
  unsigned hsync_start = profile->width + profile->h_front;
  unsigned hsync_end = hsync_start + profile->h_sync;
  unsigned htotal = hsync_end + profile->h_back;
  unsigned vsync_start = profile->height + profile->v_front;
  unsigned vsync_end = vsync_start + profile->v_sync;
  unsigned vtotal = vsync_end + profile->v_back;
  bool clock_matches = false;
  for (size_t i = 0; i < profile->clock_count; i++)
    clock_matches |= mode->clock == profile->clocks_khz[i];
  unsigned sync_flags = DRM_MODE_FLAG_PHSYNC | DRM_MODE_FLAG_NHSYNC |
                        DRM_MODE_FLAG_PVSYNC | DRM_MODE_FLAG_NVSYNC;
  unsigned allowed_flags = sync_flags;
  unsigned expected_flags = profile->h_positive ? DRM_MODE_FLAG_PHSYNC
                                                 : DRM_MODE_FLAG_NHSYNC;
  expected_flags |= profile->v_positive ? DRM_MODE_FLAG_PVSYNC
                                        : DRM_MODE_FLAG_NVSYNC;
  return mode->hdisplay == profile->width && mode->vdisplay == profile->height &&
         mode->hsync_start == hsync_start && mode->hsync_end == hsync_end &&
         mode->htotal == htotal && mode->vsync_start == vsync_start &&
         mode->vsync_end == vsync_end && mode->vtotal == vtotal &&
         (mode->flags & sync_flags) == expected_flags &&
         !(mode->flags & ~allowed_flags) &&
         clock_matches;
}
static bool crtc_used_by_other_connector(drmModeRes *resources,
                                         uint32_t selected_connector,
                                         uint32_t selected_crtc) {
  for (int i = 0; i < resources->count_connectors; i++) {
    drmModeConnector *candidate =
        drmModeGetConnector(drm_fd, resources->connectors[i]);
    if (!candidate)
      continue;
    bool conflict = false;
    if (candidate->connector_id != selected_connector && candidate->encoder_id) {
      drmModeEncoder *encoder = drmModeGetEncoder(drm_fd, candidate->encoder_id);
      conflict = encoder && encoder->crtc_id == selected_crtc;
      if (encoder)
        drmModeFreeEncoder(encoder);
    }
    drmModeFreeConnector(candidate);
    if (conflict)
      return true;
  }
  return false;
}
struct buffer {
  uint32_t handle, fb, pitch;
  uint64_t size;
  void *map;
};
static int create_buffer(int fd, struct buffer *b,
                         const struct profile *profile) {
  struct drm_mode_create_dumb c = {
      .width = profile->width, .height = profile->height, .bpp = 32};
  if (drmIoctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &c))
    return -1;
  b->handle = c.handle;
  b->pitch = c.pitch;
  b->size = c.size;
  uint32_t handles[4] = {c.handle}, pitches[4] = {c.pitch}, offsets[4] = {0};
  if (drmModeAddFB2(fd, profile->width, profile->height, DRM_FORMAT_XRGB8888,
                    handles, pitches, offsets, &b->fb, 0))
    return -1;
  struct drm_mode_map_dumb m = {.handle = c.handle};
  if (drmIoctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &m))
    return -1;
  b->map = mmap(NULL, c.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, m.offset);
  if (b->map == MAP_FAILED) {
    b->map = NULL;
    return -1;
  }
  memset(b->map, 0, b->size);
  return 0;
}
static void fill(struct buffer *b, uint32_t id,
                 const struct profile *profile) {
  for (unsigned y = 0; y < profile->height; y++) {
    uint32_t *row = (uint32_t *)((uint8_t *)b->map + y * b->pitch);
    for (unsigned x = 0; x < profile->width; x++)
      row[x] = pixel(id, x, y);
  }
}
static void flip_event(int fd, unsigned frame, unsigned sec, unsigned usec,
                       void *d) {
  (void)fd;
  (void)frame;
  (void)sec;
  (void)usec;
  *(bool *)d = false;
}
static int dispatch(int timeout) {
  struct pollfd fd = {drm_fd, POLLIN, 0};
  int r = poll(&fd, 1, timeout);
  if (r < 0)
    return errno == EINTR ? 0 : -1;
  if (fd.revents & (POLLERR | POLLHUP))
    return -1;
  if (fd.revents & POLLIN) {
    drmEventContext ctx = {.version = 2, .page_flip_handler = flip_event};
    if (drmHandleEvent(drm_fd, &ctx)) {
      perror("DRM event");
      return -1;
    }
  }
  return 0;
}
int main(int argc, char **argv) {
  int arg = 1;
  const struct profile *profile = &profiles[0];
  if (arg + 1 < argc && !strcmp(argv[arg], "--mode")) {
    profile = find_profile(argv[arg + 1]);
    if (!profile) {
      fprintf(stderr, "Unsupported mode profile\n");
      return 2;
    }
    arg += 2;
  }
  bool direct = arg < argc && !strcmp(argv[arg], "--direct");
  bool dump = arg < argc && !strcmp(argv[arg], "--dump");
  if ((!direct && !dump) || argc - arg != (direct ? 5 : 3)) {
    fprintf(stderr, "Usage: %s [--mode vga|1080p30] --dump ID SECONDS or "
                    "[--mode vga|1080p30] --direct CARD CONNECTOR ID SECONDS\n",
            argv[0]);
    return 2;
  }
  const char *target = direct ? argv[arg + 2] : argv[arg + 1];
  const char *idtext = direct ? argv[arg + 3] : argv[arg + 1];
  const char *durationtext = direct ? argv[arg + 4] : argv[arg + 2];
  char *end;
  errno = 0;
  unsigned long idarg = strtoul(idtext, &end, 10);
  if (errno || end == idtext || *end || idtext[0] == '-' || idarg > UINT32_MAX)
    return 2;
  errno = 0;
  unsigned long duration = strtoul(durationtext, &end, 10);
  if (errno || end == durationtext || *end || durationtext[0] == '-' ||
      duration < 1 || duration > 3600)
    return 2;
  uint32_t id = (uint32_t)idarg;
  if (dump) {
    for (unsigned y = 0; y < profile->height; y++)
      for (unsigned x = 0; x < profile->width; x++) {
        uint32_t p = pixel(id, x, y);
        uint8_t rgb[3] = {p >> 16, p >> 8, p};
        if (fwrite(rgb, 1, 3, stdout) != 3)
          return 1;
      }
    return 0;
  }
  signal(SIGINT, interrupted);
  signal(SIGTERM, interrupted);
  alarm((unsigned)duration +
        30); /* Bound stalled DRM setup; DRM fd closes on exit. */
  uint32_t connector_id = 0;
  drm_fd = open(argv[arg + 1], O_RDWR | O_CLOEXEC);
  if (drm_fd < 0) {
    perror("Open DRM card");
    return 1;
  }
  if (!drmIsMaster(drm_fd) && drmSetMaster(drm_fd)) {
    fprintf(stderr, "DRM master unavailable; run on an inactive-desktop VT, "
                    "never force takeover\n");
    close(drm_fd);
    return 1;
  }
  drmModeRes *r = drmModeGetResources(drm_fd);
  if (!r) {
    perror("DRM resources");
    close(drm_fd);
    return 1;
  }
  for (int i = 0; i < r->count_connectors; i++) {
    drmModeConnector *c = drmModeGetConnector(drm_fd, r->connectors[i]);
    if (!c)
      continue;
    char name[128];
    snprintf(name, sizeof name, "%s-%u",
             drmModeGetConnectorTypeName(c->connector_type),
             c->connector_type_id);
    if (!strcmp(name, target)) {
      connector_id = c->connector_id;
    }
    drmModeFreeConnector(c);
  }
  drmModeFreeResources(r);
  if (!connector_id) {
    fprintf(stderr, "Requested connector absent\n");
    close(drm_fd);
    return 1;
  }
  int result = 1;
  bool configured = false;
  uint32_t crtc = 0;
  struct buffer buffers[2] = {{0}};
  drmModeRes *res = drmModeGetResources(drm_fd);
  drmModeConnector *connector = drmModeGetConnector(drm_fd, connector_id);
  drmModeModeInfo *mode = NULL;
  if (!res || !connector || connector->connection != DRM_MODE_CONNECTED)
    goto cleanup;
  for (int i = 0; i < connector->count_modes; i++) {
    drmModeModeInfo *m = &connector->modes[i];
    if (matches_profile(m, profile)) {
      mode = m;
      break;
    }
  }
  for (int i = 0; i < connector->count_encoders && !crtc; i++) {
    drmModeEncoder *e = drmModeGetEncoder(drm_fd, connector->encoders[i]);
    if (!e)
      continue;
    if (e->encoder_id == connector->encoder_id && e->crtc_id) {
      crtc = e->crtc_id;
    } else {
      for (int j = 0; j < res->count_crtcs; j++) {
        if (!(e->possible_crtcs & (1u << j)))
          continue;
        drmModeCrtc *candidate = drmModeGetCrtc(drm_fd, res->crtcs[j]);
        if (candidate && !candidate->mode_valid && !candidate->buffer_id)
          crtc = candidate->crtc_id;
        if (candidate)
          drmModeFreeCrtc(candidate);
        if (crtc)
          break;
      }
    }
    drmModeFreeEncoder(e);
  }
  if (!mode) {
    fprintf(stderr, "Connector does not advertise the exact %s timing\n",
            profile->name);
    goto cleanup;
  }
  if (!crtc)
    goto cleanup;
  if (crtc_used_by_other_connector(res, connector_id, crtc)) {
    fprintf(stderr, "Selected CRTC is shared with another connector\n");
    goto cleanup;
  }
  if (create_buffer(drm_fd, &buffers[0], profile) ||
      create_buffer(drm_fd, &buffers[1], profile))
    goto cleanup;
  fill(&buffers[0], id, profile);
  if (drmModeSetCrtc(drm_fd, crtc, buffers[0].fb, 0, 0, &connector_id, 1, mode))
    goto cleanup;
  configured = true;
  double refresh = (double)mode->clock * 1000.0 / mode->htotal / mode->vtotal;
  printf("{\"event\":\"kms_ready\",\"mode\":\"%s\",\"connector_id\":%u,"
         "\"crtc\":%u,\"format\":\"XR24\",\"clock_khz\":%u,"
         "\"width\":%u,\"height\":%u,\"refresh_hz\":%.6f,"
         "\"h_total\":%u,\"v_total\":%u,\"h_front_porch\":%u,"
         "\"h_sync_width\":%u,\"h_back_porch\":%u,"
         "\"h_sync_positive\":%s,\"v_front_porch\":%u,"
         "\"v_sync_width\":%u,\"v_back_porch\":%u,"
         "\"v_sync_positive\":%s}\n",
         profile->name, connector_id, crtc, mode->clock, profile->width,
         profile->height, refresh, mode->htotal, mode->vtotal, profile->h_front,
         profile->h_sync, profile->h_back,
         profile->h_positive ? "true" : "false", profile->v_front,
         profile->v_sync, profile->v_back,
         profile->v_positive ? "true" : "false");
  fflush(stdout);
  double start = now(), last = start;
  unsigned current = 0;
  while (!stop && now() - start < duration) {
    if (dispatch(10))
      goto cleanup;
    if (now() - last < 0.25)
      continue;
    if (id == UINT32_MAX) {
      fprintf(stderr, "Source ID wrap refused\n");
      goto cleanup;
    }
    unsigned next = current ^ 1;
    fill(&buffers[next], ++id, profile);
    double generated = now();
    bool pending = true;
    if (drmModePageFlip(drm_fd, crtc, buffers[next].fb,
                        DRM_MODE_PAGE_FLIP_EVENT, &pending)) {
      perror("DRM page flip");
      goto cleanup;
    }
    double deadline = now() + 2;
    while (pending && now() < deadline && !stop)
      if (dispatch(100))
        goto cleanup;
    if (pending) {
      fprintf(stderr, "Page flip incomplete\n");
      goto cleanup;
    }
    current = next;
    last = now();
    printf("{\"event\":\"kms_presented\",\"frame_id\":%u,\"generated_"
           "monotonic\":%.9f,\"presented_monotonic\":%.9f}\n",
           id, generated, last);
    fflush(stdout);
  }
  result = 0;
cleanup:
  if (result)
    fprintf(stderr, "KMS failure: %s\n", strerror(errno));
  /* Disable only the selected CRTC before releasing scanout storage. */
  if (configured && drmModeSetCrtc(drm_fd, crtc, 0, 0, 0, NULL, 0, NULL))
    result = 1;
  for (unsigned i = 0; i < 2; i++) {
    if (buffers[i].map)
      munmap(buffers[i].map, buffers[i].size);
    if (buffers[i].fb)
      drmModeRmFB(drm_fd, buffers[i].fb);
    if (buffers[i].handle) {
      struct drm_mode_destroy_dumb d = {.handle = buffers[i].handle};
      drmIoctl(drm_fd, DRM_IOCTL_MODE_DESTROY_DUMB, &d);
    }
  }
  if (connector)
    drmModeFreeConnector(connector);
  if (res)
    drmModeFreeResources(res);
  close(drm_fd);
  return result;
}
