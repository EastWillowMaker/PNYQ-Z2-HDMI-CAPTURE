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

#define W 640
#define H 480
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
struct buffer {
  uint32_t handle, fb, pitch;
  uint64_t size;
  void *map;
};
static int create_buffer(int fd, struct buffer *b) {
  struct drm_mode_create_dumb c = {.width = W, .height = H, .bpp = 32};
  if (drmIoctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &c))
    return -1;
  b->handle = c.handle;
  b->pitch = c.pitch;
  b->size = c.size;
  uint32_t handles[4] = {c.handle}, pitches[4] = {c.pitch}, offsets[4] = {0};
  if (drmModeAddFB2(fd, W, H, DRM_FORMAT_XRGB8888, handles, pitches, offsets,
                    &b->fb, 0))
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
static void fill(struct buffer *b, uint32_t id) {
  for (unsigned y = 0; y < H; y++) {
    uint32_t *row = (uint32_t *)((uint8_t *)b->map + y * b->pitch);
    for (unsigned x = 0; x < W; x++)
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
  bool direct = argc == 6 && !strcmp(argv[1], "--direct");
  if (!direct && !(argc == 4 && !strcmp(argv[1], "--dump"))) {
    fprintf(
        stderr,
        "Usage: %s --dump ID SECONDS or --direct CARD CONNECTOR ID SECONDS\n",
        argv[0]);
    return 2;
  }
  const char *target = argv[direct ? 3 : 1], *idtext = argv[direct ? 4 : 2],
             *durationtext = argv[direct ? 5 : 3];
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
  if (!strcmp(argv[1], "--dump")) {
    for (unsigned y = 0; y < H; y++)
      for (unsigned x = 0; x < W; x++) {
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
  drm_fd = open(argv[2], O_RDWR | O_CLOEXEC);
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
    double hz = (double)m->clock * 1000 / m->htotal / m->vtotal;
    if (m->hdisplay == W && m->vdisplay == H && hz > 59.9 && hz < 60.1 &&
        !(m->flags & (DRM_MODE_FLAG_INTERLACE | DRM_MODE_FLAG_DBLSCAN))) {
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
  if (!mode || !crtc || create_buffer(drm_fd, &buffers[0]) ||
      create_buffer(drm_fd, &buffers[1]))
    goto cleanup;
  fill(&buffers[0], id);
  if (drmModeSetCrtc(drm_fd, crtc, buffers[0].fb, 0, 0, &connector_id, 1, mode))
    goto cleanup;
  configured = true;
  printf("{\"event\":\"kms_ready\",\"connector_id\":%u,\"crtc\":%u,\"format\":"
         "\"XR24\",\"clock_khz\":%u,\"width\":640,\"height\":480}\n",
         connector_id, crtc, mode->clock);
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
    fill(&buffers[next], ++id);
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
